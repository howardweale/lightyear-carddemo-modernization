from __future__ import annotations

import hashlib
import json
import ssl
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol
from urllib.parse import parse_qsl, urlsplit

from .contracts import (
    ExtensionContractError,
    canonical_hash,
    finalize_envelope,
    validate_envelope,
)


CAMPAIGN_SCHEMA_VERSION = "1.0"
REQUIRED_ADAPTERS = (
    "lightyear.cics-cmci",
    "lightyear.db2-zos-catalog",
    "lightyear.zosmf-jobs",
)
ADAPTER_VERSIONS = {
    "lightyear.cics-cmci": "1.0",
    "lightyear.db2-zos-catalog": "1.0",
    "lightyear.zosmf-jobs": "1.1",
}
CONTENT_TYPES = {
    "lightyear.cics-cmci": ("application/xml", "text/xml"),
    "lightyear.db2-zos-catalog": ("application/json",),
    "lightyear.zosmf-jobs": ("application/json",),
}
ENTITY_KEYS = {
    "lightyear.cics-cmci": {"program", "transaction"},
    "lightyear.db2-zos-catalog": {"table"},
    "lightyear.zosmf-jobs": {"job", "program"},
}
PATH_PREFIXES = {
    "lightyear.cics-cmci": "/CICSSystemManagement/",
    "lightyear.db2-zos-catalog": "/lightyear/db2/catalog/",
    "lightyear.zosmf-jobs": "/zosmf/restjobs/jobs/",
}


class CampaignError(ExtensionContractError):
    """Raised when a mainframe access campaign crosses a trust boundary."""


@dataclass(frozen=True)
class BoundedResponse:
    status: int
    content_type: str
    body: bytes


class ReadOnlyTransport(Protocol):
    def get(self, path: str, accepted_types: tuple[str, ...]) -> BoundedResponse: ...


class _RejectRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Mapping[str, str],
        newurl: str,
    ) -> None:
        raise CampaignError("Mainframe access endpoint attempted a redirect")


class BoundedHttpTransport:
    """GET-only HTTPS transport that keeps credentials and response bodies out of evidence."""

    def __init__(
        self,
        base_url: str,
        bearer_token: str,
        *,
        timeout_seconds: int = 15,
        max_response_bytes: int = 65_536,
        ca_file: Path | None = None,
        opener: Callable[..., Any] | None = None,
    ) -> None:
        parsed = urlsplit(base_url)
        if (
            parsed.scheme != "https"
            or not parsed.netloc
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise CampaignError("Mainframe access base URL must be credential-free HTTPS")
        if not bearer_token.strip():
            raise CampaignError("Mainframe access bearer credential is empty")
        if not 1 <= timeout_seconds <= 120:
            raise CampaignError("Mainframe access timeout must be between 1 and 120 seconds")
        if not 1_024 <= max_response_bytes <= 1_048_576:
            raise CampaignError("Mainframe access response bound must be 1 KiB to 1 MiB")
        self.base_url = base_url.rstrip("/")
        self._bearer_token = bearer_token
        self.timeout_seconds = timeout_seconds
        self.max_response_bytes = max_response_bytes
        if opener is None:
            context = ssl.create_default_context(cafile=str(ca_file) if ca_file else None)
            context.minimum_version = ssl.TLSVersion.TLSv1_2
            opener = urllib.request.build_opener(
                urllib.request.HTTPSHandler(context=context),
                _RejectRedirects(),
            ).open
        self._open = opener

    def get(self, path: str, accepted_types: tuple[str, ...]) -> BoundedResponse:
        _validate_path(path)
        request = urllib.request.Request(
            self.base_url + path,
            headers={
                "Accept": ", ".join(accepted_types),
                "Authorization": f"Bearer {self._bearer_token}",
                "User-Agent": "LIGHTYEAR-mainframe-access/1.0",
            },
            method="GET",
        )
        try:
            with self._open(request, timeout=self.timeout_seconds) as response:
                status = int(response.getcode())
                content_type = str(response.headers.get_content_type()).lower()
                body = response.read(self.max_response_bytes + 1)
        except CampaignError:
            raise
        except (OSError, urllib.error.URLError) as exc:
            raise CampaignError(
                f"Mainframe access request failed: {type(exc).__name__}"
            ) from None
        if status != 200:
            raise CampaignError(f"Mainframe access request returned HTTP {status}")
        if content_type not in accepted_types:
            raise CampaignError(f"Mainframe access response type is not allowed: {content_type}")
        if len(body) > self.max_response_bytes:
            raise CampaignError("Mainframe access response exceeded the configured byte bound")
        return BoundedResponse(status, content_type, body)


class FixtureTransport:
    """Deterministic response transport for CI; it can never claim live evidence."""

    def __init__(self, fixture: Mapping[str, Any], max_response_bytes: int = 65_536) -> None:
        self.fixture = fixture
        self.max_response_bytes = max_response_bytes

    def get(self, path: str, accepted_types: tuple[str, ...]) -> BoundedResponse:
        _validate_path(path)
        responses = self.fixture.get("responses", {})
        item = responses.get(path) if isinstance(responses, dict) else None
        if not isinstance(item, dict):
            raise CampaignError(f"Fixture has no bounded response for path: {path}")
        status = int(item.get("status", 0))
        content_type = str(item.get("content_type", "")).lower()
        body_value = item.get("body")
        if isinstance(body_value, dict):
            body = json.dumps(body_value, sort_keys=True, separators=(",", ":")).encode()
        elif isinstance(body_value, str):
            body = body_value.encode()
        else:
            raise CampaignError(f"Fixture response body is invalid for path: {path}")
        if status != 200:
            raise CampaignError(f"Fixture response returned HTTP {status}")
        if content_type not in accepted_types:
            raise CampaignError(f"Fixture response type is not allowed: {content_type}")
        if len(body) > self.max_response_bytes:
            raise CampaignError("Fixture response exceeded the configured byte bound")
        return BoundedResponse(status, content_type, body)


def load_profile(path: Path) -> dict[str, Any]:
    profile = json.loads(path.read_text(encoding="utf-8"))
    errors = validate_profile(profile)
    if errors:
        raise CampaignError("; ".join(errors))
    return profile


def validate_profile(profile: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    required = {"schema_version", "profile_id", "source_system", "adapters", "bounds"}
    missing = sorted(required - set(profile))
    if missing:
        return [f"access profile is missing required fields: {', '.join(missing)}"]
    if profile.get("schema_version") != CAMPAIGN_SCHEMA_VERSION:
        errors.append("access profile schema_version is unsupported")
    extras = sorted(set(profile) - required)
    if extras:
        errors.append(f"access profile has unsupported fields: {', '.join(extras)}")
    for field in ("profile_id", "source_system"):
        value = profile.get(field)
        if not isinstance(value, str) or not value.strip() or len(value) > 128:
            errors.append(f"access profile {field} is invalid")
    adapters = profile.get("adapters")
    if not isinstance(adapters, dict) or set(adapters) != set(REQUIRED_ADAPTERS):
        errors.append("access profile must configure the exact required adapter set")
        adapters = {}
    for adapter_id in REQUIRED_ADAPTERS:
        item = adapters.get(adapter_id)
        if not isinstance(item, dict):
            continue
        path = item.get("path")
        try:
            _validate_path(path)
        except CampaignError as exc:
            errors.append(f"{adapter_id}: {exc}")
        else:
            parsed = urlsplit(path)
            if not parsed.path.startswith(PATH_PREFIXES[adapter_id]):
                errors.append(f"{adapter_id} path has an invalid resource prefix")
            if adapter_id != "lightyear.zosmf-jobs" and parsed.query:
                errors.append(f"{adapter_id} path must not include a query")
        entities = item.get("entities")
        if not isinstance(entities, dict) or set(entities) != ENTITY_KEYS[adapter_id]:
            errors.append(f"{adapter_id} requires the exact graph entity bindings")
        elif not all(isinstance(value, str) and value for value in entities.values()):
            errors.append(f"{adapter_id} graph entity bindings are invalid")
    bounds = profile.get("bounds")
    if not isinstance(bounds, dict):
        errors.append("access profile bounds are invalid")
    else:
        timeout = bounds.get("timeout_seconds")
        maximum = bounds.get("max_response_bytes")
        if not isinstance(timeout, int) or not 1 <= timeout <= 120:
            errors.append("access profile timeout_seconds is invalid")
        if not isinstance(maximum, int) or not 1_024 <= maximum <= 1_048_576:
            errors.append("access profile max_response_bytes is invalid")
    serialized = json.dumps(profile, sort_keys=True).lower()
    if any(name in serialized for name in ('"password"', '"token"', '"authorization"', '"secret"')):
        errors.append("access profile must not contain credential-shaped fields")
    return errors


def collect_campaign(
    profile: Mapping[str, Any],
    graph: Mapping[str, Any],
    transport: ReadOnlyTransport,
    *,
    evidence_class: str,
    collected_at: str | None = None,
    signing_key: bytes | None = None,
    key_id: str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    profile_errors = validate_profile(profile)
    if profile_errors:
        raise CampaignError("; ".join(profile_errors))
    if evidence_class not in {"live", "simulated"}:
        raise CampaignError("Campaign collection evidence_class must be live or simulated")
    if evidence_class == "live" and (signing_key is None or key_id is None):
        raise CampaignError("Live campaign collection requires an evidence signing key")
    timestamp = collected_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    if evidence_class == "simulated" and collected_at is None:
        raise CampaignError("Simulated campaign collection requires a deterministic timestamp")

    captures: list[dict[str, Any]] = []
    for adapter_id in REQUIRED_ADAPTERS:
        config = profile["adapters"][adapter_id]
        response = transport.get(config["path"], CONTENT_TYPES[adapter_id])
        claims = _claims(adapter_id, response.body, config["entities"])
        payload = {
            "schema_version": "1.0",
            "envelope_type": "lightyear-adapter-evidence",
            "envelope_id": f"capture:{adapter_id.split('.')[-1]}:{profile['profile_id']}",
            "adapter": {"id": adapter_id, "version": ADAPTER_VERSIONS[adapter_id]},
            "source": {
                "system": profile["source_system"],
                "kind": "remote-mainframe" if evidence_class == "live" else "campaign-simulator",
                "attestation": "remote-verified" if evidence_class == "live" else "local-simulator",
            },
            "collected_at": timestamp,
            "evidence_class": evidence_class,
            "graph_binding": {
                "graph_id": graph["graph_id"],
                "content_sha256": graph["content_sha256"],
            },
            "scope": {
                "read_only": True,
                "mode": "live-capture" if evidence_class == "live" else "fixture-capture",
                "resources": [adapter_id],
            },
            "claims": claims,
            "artifacts": [{
                "kind": _artifact_kind(adapter_id),
                "sha256": hashlib.sha256(response.body).hexdigest(),
                "content_retained": False,
            }],
            "limitations": _limitations(evidence_class),
        }
        capture = finalize_envelope(payload, signing_key=signing_key, key_id=key_id)
        errors = validate_envelope(
            capture,
            graph=graph,
            trusted_keys={key_id: signing_key} if signing_key is not None and key_id else None,
        )
        if errors:
            raise CampaignError(f"{adapter_id}: {'; '.join(errors)}")
        captures.append(capture)
    receipt = build_campaign_receipt(profile, graph, captures, trusted_keys={key_id: signing_key} if signing_key is not None and key_id else None)
    return captures, receipt


def build_campaign_receipt(
    profile: Mapping[str, Any],
    graph: Mapping[str, Any],
    captures: list[Mapping[str, Any]],
    *,
    trusted_keys: Mapping[str, bytes] | None = None,
) -> dict[str, Any]:
    adapter_ids = [str(item.get("adapter", {}).get("id", "")) for item in captures]
    classes = {str(item.get("evidence_class", "")) for item in captures}
    capture_errors = [
        error
        for capture in captures
        for error in validate_envelope(capture, graph=graph, trusted_keys=trusted_keys)
    ]
    checks = {
        "exact_adapter_set": sorted(adapter_ids) == sorted(REQUIRED_ADAPTERS),
        "unique_adapters": len(adapter_ids) == len(set(adapter_ids)),
        "all_captures_valid": not capture_errors,
        "all_graph_bound": all(item.get("graph_binding", {}).get("content_sha256") == graph.get("content_sha256") for item in captures),
        "all_read_only": all(item.get("scope", {}).get("read_only") is True for item in captures),
        "consistent_evidence_class": len(classes) == 1 and classes <= {"live", "simulated"},
        "live_signatures_trusted": "live" not in classes or all(item.get("signature") is not None for item in captures),
    }
    status = "passed" if all(checks.values()) else "failed"
    evidence_class = next(iter(classes)) if len(classes) == 1 else "mixed"
    payload: dict[str, Any] = {
        "schema_version": CAMPAIGN_SCHEMA_VERSION,
        "receipt_type": "lightyear-mainframe-access-campaign",
        "campaign_id": f"campaign:{profile['profile_id']}",
        "profile_id": profile["profile_id"],
        "source_system": profile["source_system"],
        "graph_binding": {
            "graph_id": graph["graph_id"],
            "content_sha256": graph["content_sha256"],
        },
        "evidence_class": evidence_class,
        "required_adapters": list(REQUIRED_ADAPTERS),
        "captures": [{
            "adapter_id": item["adapter"]["id"],
            "content_sha256": item["content_sha256"],
            "evidence_class": item["evidence_class"],
        } for item in sorted(captures, key=lambda value: value["adapter"]["id"])],
        "checks": checks,
        "errors": sorted(set(capture_errors)),
        "production_ready": False,
        "limitations": [
            "A passing campaign proves bounded read-only observations, not modernization equivalence.",
            "Production promotion still requires customer-authorized baselines, policy approval, and cutover evidence.",
        ],
        "status": status,
    }
    payload["content_sha256"] = canonical_hash(payload)
    return payload


def validate_campaign_receipt(
    receipt: Mapping[str, Any],
    profile: Mapping[str, Any],
    graph: Mapping[str, Any],
    captures: list[Mapping[str, Any]],
    *,
    trusted_keys: Mapping[str, bytes] | None = None,
) -> list[str]:
    expected = build_campaign_receipt(profile, graph, captures, trusted_keys=trusted_keys)
    errors: list[str] = []
    for field in (
        "schema_version", "receipt_type", "campaign_id", "profile_id", "source_system",
        "graph_binding", "evidence_class", "required_adapters", "captures", "checks",
        "errors", "production_ready", "limitations", "status", "content_sha256",
    ):
        if receipt.get(field) != expected.get(field):
            errors.append(f"campaign receipt field differs: {field}")
    return errors


def _claims(adapter_id: str, body: bytes, entities: Mapping[str, str]) -> list[dict[str, Any]]:
    if adapter_id == "lightyear.zosmf-jobs":
        value = _json_object(body, adapter_id)
        required = ("jobname", "jobid", "status", "retcode")
        _require_scalars(value, required, adapter_id)
        if not all(isinstance(value[key], str) for key in required):
            raise CampaignError("z/OSMF job identity and status fields must be strings")
        steps = value.get("step-data")
        if not isinstance(steps, list) or len(steps) != 1 or not isinstance(steps[0], dict):
            raise CampaignError("z/OSMF response requires exactly one bounded step-data record")
        step = steps[0]
        _require_scalars(step, ("step-name", "program-name", "completion-code"), adapter_id)
        _expect_entity_suffix(entities, "job", value["jobname"], adapter_id)
        _expect_entity_suffix(entities, "program", step["program-name"], adapter_id)
        return [
            _claim(entities, "job", "job_status_observed", {
                "job_name": value["jobname"], "job_id": value["jobid"],
                "status": value["status"], "completion_code": value["retcode"],
            }),
            _claim(entities, "program", "job_step_program_observed", {
                "step": step["step-name"], "program": step["program-name"],
                "completion_code": step["completion-code"],
            }),
        ]
    if adapter_id == "lightyear.db2-zos-catalog":
        value = _json_object(body, adapter_id)
        required = ("schema", "table", "column_count", "primary_key", "index_count", "package_count")
        _require_scalars(value, required, adapter_id, allow_lists={"primary_key"})
        if set(value) != set(required):
            raise CampaignError("Db2 catalog response must contain the exact bounded projection")
        if not isinstance(value["schema"], str) or not isinstance(value["table"], str):
            raise CampaignError("Db2 catalog table identity is invalid")
        if not isinstance(value["column_count"], int) or value["column_count"] < 1:
            raise CampaignError("Db2 catalog column_count is invalid")
        if any(not isinstance(value[key], int) or value[key] < 0 for key in ("index_count", "package_count")):
            raise CampaignError("Db2 catalog index or package count is invalid")
        if not isinstance(value["primary_key"], list) or not value["primary_key"]:
            raise CampaignError("Db2 catalog primary_key is invalid")
        _expect_entity_suffix(
            entities, "table", f"{value['schema']}.{value['table']}", adapter_id
        )
        return [_claim(entities, "table", "db2_catalog_observed", {
            "schema": value["schema"], "table": value["table"],
            "column_count": value["column_count"], "primary_key": value["primary_key"],
            "index_count": value["index_count"], "package_count": value["package_count"],
        })]
    if adapter_id == "lightyear.cics-cmci":
        try:
            root = ET.fromstring(body)
        except ET.ParseError:
            raise CampaignError("CICS CMCI response is malformed XML") from None
        transaction = next(
            (item for item in root.iter() if _local_name(item.tag) in {
                "transaction", "cicslocaltransaction",
            }),
            None,
        )
        if transaction is None:
            raise CampaignError("CICS CMCI response is missing bounded resource metadata")
        details = {
            "applid": transaction.get("applid"),
            "transaction": transaction.get("tranid") or transaction.get("name"),
            "program": transaction.get("program"),
            "enabled": transaction.get("enablestatus") or transaction.get("enabled"),
        }
        if not all(isinstance(value, str) and value and len(value) <= 128 for value in details.values()):
            raise CampaignError("CICS CMCI response metadata is invalid")
        _expect_entity_suffix(entities, "transaction", details["transaction"], adapter_id)
        _expect_entity_suffix(entities, "program", details["program"], adapter_id)
        return [
            _claim(entities, "transaction", "cics_transaction_observed", details),
            _claim(entities, "program", "cics_program_binding_observed", {
                "program": details["program"], "region": details["applid"],
            }),
        ]
    raise CampaignError(f"Unsupported campaign adapter: {adapter_id}")


def _claim(entities: Mapping[str, str], key: str, operation: str, details: Mapping[str, Any]) -> dict[str, Any]:
    entity_id = entities.get(key)
    if not entity_id:
        raise CampaignError(f"Access profile is missing graph entity binding: {key}")
    return {
        "entity_kind": "node",
        "entity_id": entity_id,
        "assertion": "observed",
        "operation": operation,
        "details": dict(details),
    }


def _json_object(body: bytes, adapter_id: str) -> dict[str, Any]:
    try:
        value = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise CampaignError(f"{adapter_id} response is malformed JSON") from None
    if not isinstance(value, dict):
        raise CampaignError(f"{adapter_id} response must be a JSON object")
    return value


def _require_scalars(
    value: Mapping[str, Any],
    required: tuple[str, ...],
    adapter_id: str,
    *,
    allow_lists: set[str] | None = None,
) -> None:
    allow_lists = allow_lists or set()
    for key in required:
        item = value.get(key)
        if key in allow_lists:
            if not isinstance(item, list) or not item or not all(isinstance(part, str) and 0 < len(part) <= 128 for part in item):
                raise CampaignError(f"{adapter_id} response field is invalid: {key}")
        elif not isinstance(item, (str, int)) or isinstance(item, str) and (not item or len(item) > 128):
            raise CampaignError(f"{adapter_id} response field is invalid: {key}")


def _artifact_kind(adapter_id: str) -> str:
    return {
        "lightyear.zosmf-jobs": "zosmf-job-response",
        "lightyear.db2-zos-catalog": "db2-zos-catalog-response",
        "lightyear.cics-cmci": "cics-cmci-response",
    }[adapter_id]


def _limitations(evidence_class: str) -> list[str]:
    common = "Raw response bodies are hashed and discarded; only bounded graph-addressed claims are retained."
    if evidence_class == "live":
        return [common, "This read-only capture does not authorize mutation or prove production equivalence."]
    return [common, "This capture used deterministic simulated responses, not a customer mainframe."]


def _validate_path(path: Any) -> None:
    parsed = urlsplit(path) if isinstance(path, str) else None
    query = parse_qsl(parsed.query, keep_blank_values=True) if parsed else []
    if (
        not isinstance(path, str)
        or not path.startswith("/")
        or len(path) > 512
        or parsed is None
        or parsed.scheme
        or parsed.netloc
        or ".." in parsed.path.split("/")
        or parsed.fragment
        or "@" in path
        or len(query) != len(set(query))
        or any(key not in {"step-data", "exec-data"} or value != "Y" for key, value in query)
    ):
        raise CampaignError("Mainframe access path must be a bounded credential-free absolute path")


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _expect_entity_suffix(
    entities: Mapping[str, str], key: str, observed: str, adapter_id: str
) -> None:
    expected = entities.get(key, "").rsplit(":", 1)[-1]
    if observed.upper() != expected.upper():
        raise CampaignError(f"{adapter_id} returned a different {key} identity")
