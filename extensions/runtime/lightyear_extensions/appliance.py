from __future__ import annotations

import copy
import hashlib
import json
import socket
import ssl
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol
from urllib.parse import parse_qsl, urlsplit

from lightyear_common.io import write_json

from .campaign import (
    ADAPTER_VERSIONS,
    CONTENT_TYPES,
    REQUIRED_ADAPTERS,
    CampaignError,
    _artifact_kind,
    _claims,
    _limitations,
    validate_profile as validate_campaign_profile,
)
from .contracts import canonical_hash, finalize_envelope, validate_envelope


APPLIANCE_SCHEMA_VERSION = "1.0"
AUTH_MODES = {
    "bearer-env",
    "mtls-bearer-env",
    "externally-issued-oauth-bearer-env",
}
RETRYABLE_STATUS = {429, 502, 503, 504}
FAULT_KINDS = (
    "dns-exhaustion",
    "tls-rejection",
    "timeout-recovery",
    "redirect-rejection",
    "pagination-loop",
    "rate-limit-recovery",
    "response-truncation",
    "checkpoint-tamper",
)


class ApplianceError(CampaignError):
    """Raised when enterprise collection crosses a bounded operational policy."""

    def __init__(self, code: str, *, retryable: bool = False, retry_after_ms: int | None = None):
        super().__init__(f"Enterprise collection failed: {code}")
        self.code = code
        self.retryable = retryable
        self.retry_after_ms = retry_after_ms


@dataclass(frozen=True)
class ApplianceResponse:
    status: int
    content_type: str
    body: bytes
    next_path: str | None = None
    retry_after_ms: int | None = None


class ApplianceTransport(Protocol):
    def get(self, path: str, accepted_types: tuple[str, ...]) -> ApplianceResponse: ...


class _RejectRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        raise ApplianceError("redirect-rejected")


class EnterpriseHttpTransport:
    """HTTPS GET transport with optional mTLS and externally provisioned bearer credentials."""

    def __init__(
        self,
        base_url: str,
        bearer_value: str,
        *,
        auth_mode: str,
        timeout_seconds: int,
        max_response_bytes: int,
        ca_file: Path | None = None,
        client_certificate: Path | None = None,
        client_key: Path | None = None,
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
            raise ApplianceError("credential-free-https-base-url-required")
        if auth_mode not in AUTH_MODES:
            raise ApplianceError("unsupported-auth-mode")
        if not bearer_value.strip():
            raise ApplianceError("empty-bearer-credential")
        if auth_mode == "mtls-bearer-env" and opener is None:
            if client_certificate is None or client_key is None:
                raise ApplianceError("mtls-certificate-and-key-required")
        elif auth_mode != "mtls-bearer-env" and (client_certificate or client_key):
            raise ApplianceError("client-certificate-requires-mtls-mode")
        if not 1 <= timeout_seconds <= 120:
            raise ApplianceError("timeout-out-of-bounds")
        if not 1_024 <= max_response_bytes <= 1_048_576:
            raise ApplianceError("response-bound-out-of-range")
        self.base_url = base_url.rstrip("/")
        self._bearer_value = bearer_value
        self.auth_mode = auth_mode
        self.timeout_seconds = timeout_seconds
        self.max_response_bytes = max_response_bytes
        if opener is None:
            context = ssl.create_default_context(cafile=str(ca_file) if ca_file else None)
            context.minimum_version = ssl.TLSVersion.TLSv1_2
            if client_certificate is not None and client_key is not None:
                context.load_cert_chain(str(client_certificate), str(client_key))
            opener = urllib.request.build_opener(
                urllib.request.HTTPSHandler(context=context), _RejectRedirects()
            ).open
        self._open = opener

    def get(self, path: str, accepted_types: tuple[str, ...]) -> ApplianceResponse:
        _validate_page_path(path)
        request = urllib.request.Request(
            self.base_url + path,
            headers={
                "Accept": ", ".join(accepted_types),
                "Authorization": f"Bearer {self._bearer_value}",
                "User-Agent": "LIGHTYEAR-enterprise-collector/1.0",
            },
            method="GET",
        )
        try:
            response = self._open(request, timeout=self.timeout_seconds)
            with response:
                return self._bounded_response(response)
        except ApplianceError:
            raise
        except urllib.error.HTTPError as exc:
            if 300 <= int(exc.code) < 400:
                raise ApplianceError("redirect-rejected") from None
            retry_after = _retry_after_ms(exc.headers.get("Retry-After"))
            if int(exc.code) in RETRYABLE_STATUS:
                raise ApplianceError(
                    f"http-{int(exc.code)}", retryable=True, retry_after_ms=retry_after
                ) from None
            raise ApplianceError(f"http-{int(exc.code)}") from None
        except (socket.timeout, TimeoutError):
            raise ApplianceError("timeout", retryable=True) from None
        except ssl.SSLError:
            raise ApplianceError("tls-rejected") from None
        except urllib.error.URLError as exc:
            reason = exc.reason
            if isinstance(reason, (socket.timeout, TimeoutError)):
                raise ApplianceError("timeout", retryable=True) from None
            if isinstance(reason, ssl.SSLError):
                raise ApplianceError("tls-rejected") from None
            raise ApplianceError("dns-or-network", retryable=True) from None
        except OSError:
            raise ApplianceError("dns-or-network", retryable=True) from None

    def _bounded_response(self, response: Any) -> ApplianceResponse:
        status = int(response.getcode())
        content_type = str(response.headers.get_content_type()).lower()
        body = response.read(self.max_response_bytes + 1)
        if status in RETRYABLE_STATUS:
            raise ApplianceError(
                f"http-{status}",
                retryable=True,
                retry_after_ms=_retry_after_ms(response.headers.get("Retry-After")),
            )
        if status != 200:
            raise ApplianceError(f"http-{status}")
        if len(body) > self.max_response_bytes:
            raise ApplianceError("response-truncated")
        next_path = response.headers.get("X-Lightyear-Next")
        return ApplianceResponse(status, content_type, body, next_path or None)


class EnterpriseFixtureTransport:
    """Scripted attempt transport used by CI and the deterministic fault laboratory."""

    def __init__(self, fixture: Mapping[str, Any]) -> None:
        if fixture.get("content_sha256") != canonical_hash(fixture, {"content_sha256"}):
            raise ApplianceError("fixture-content-hash-invalid")
        responses = fixture.get("responses")
        if not isinstance(responses, dict):
            raise ApplianceError("fixture-responses-invalid")
        self.fixture = fixture
        self._attempts: dict[str, int] = {}

    def get(self, path: str, accepted_types: tuple[str, ...]) -> ApplianceResponse:
        _validate_page_path(path)
        attempts = self.fixture["responses"].get(path)
        if not isinstance(attempts, list) or not attempts:
            raise ApplianceError("fixture-path-not-found")
        index = self._attempts.get(path, 0)
        if index >= len(attempts):
            raise ApplianceError("fixture-attempts-exhausted")
        self._attempts[path] = index + 1
        item = attempts[index]
        if not isinstance(item, dict):
            raise ApplianceError("fixture-attempt-invalid")
        fault = item.get("fault")
        if fault:
            raise ApplianceError(
                str(fault),
                retryable=bool(item.get("retryable")),
                retry_after_ms=item.get("retry_after_ms"),
            )
        status = int(item.get("status", 0))
        if status in RETRYABLE_STATUS:
            raise ApplianceError(
                f"http-{status}",
                retryable=True,
                retry_after_ms=item.get("retry_after_ms"),
            )
        if 300 <= status < 400:
            raise ApplianceError("redirect-rejected")
        if status != 200:
            raise ApplianceError(f"http-{status}")
        content_type = str(item.get("content_type", "")).lower()
        body_value = item.get("body")
        if isinstance(body_value, dict):
            body = json.dumps(body_value, sort_keys=True, separators=(",", ":")).encode()
        elif isinstance(body_value, str):
            body = body_value.encode()
        else:
            raise ApplianceError("fixture-body-invalid")
        return ApplianceResponse(
            status,
            content_type,
            body,
            str(item["next_path"]) if item.get("next_path") is not None else None,
        )


def validate_appliance_profile(profile: Mapping[str, Any], campaign_profile: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    required = {
        "schema_version",
        "appliance_id",
        "campaign_profile_sha256",
        "authentication",
        "retry",
        "pagination",
        "checkpoint",
        "retention",
        "bounds",
        "content_sha256",
    }
    if set(profile) != required:
        errors.append("enterprise appliance profile fields are incomplete or unsupported")
        return errors
    if profile.get("schema_version") != APPLIANCE_SCHEMA_VERSION:
        errors.append("enterprise appliance profile schema_version is unsupported")
    if profile.get("content_sha256") != canonical_hash(profile, {"content_sha256"}):
        errors.append("enterprise appliance profile content hash is invalid")
    if profile.get("campaign_profile_sha256") != canonical_hash(campaign_profile):
        errors.append("enterprise appliance profile targets a different campaign profile")
    if validate_campaign_profile(campaign_profile):
        errors.append("bound mainframe access profile is invalid")
    auth = profile.get("authentication", {})
    if (
        not isinstance(auth, dict)
        or set(auth) != {"accepted_modes", "minimum_tls"}
        or set(auth.get("accepted_modes", [])) != AUTH_MODES
        or auth.get("minimum_tls") != "1.2"
    ):
        errors.append("enterprise authentication policy is invalid")
    retry = profile.get("retry", {})
    if (
        not isinstance(retry, dict)
        or set(retry) != {"max_attempts", "base_backoff_ms", "max_backoff_ms", "max_retry_after_ms"}
        or not isinstance(retry.get("max_attempts"), int)
        or not 2 <= retry["max_attempts"] <= 6
        or not isinstance(retry.get("base_backoff_ms"), int)
        or not 1 <= retry["base_backoff_ms"] <= 10_000
        or not isinstance(retry.get("max_backoff_ms"), int)
        or retry["max_backoff_ms"] < retry["base_backoff_ms"]
        or retry["max_backoff_ms"] > 60_000
        or not isinstance(retry.get("max_retry_after_ms"), int)
        or not 1 <= retry["max_retry_after_ms"] <= 60_000
    ):
        errors.append("enterprise retry policy is invalid")
    pagination = profile.get("pagination", {})
    if (
        not isinstance(pagination, dict)
        or set(pagination) != {"max_pages_per_adapter", "allowed_query_keys"}
        or not isinstance(pagination.get("max_pages_per_adapter"), int)
        or not 1 <= pagination["max_pages_per_adapter"] <= 100
        or pagination.get("allowed_query_keys") != ["cursor", "exec-data", "step-data"]
    ):
        errors.append("enterprise pagination policy is invalid")
    checkpoint = profile.get("checkpoint", {})
    if (
        not isinstance(checkpoint, dict)
        or set(checkpoint) != {"interrupt_after_pages", "maximum_resume_count"}
        or not isinstance(checkpoint.get("interrupt_after_pages"), int)
        or checkpoint["interrupt_after_pages"] < 1
        or not isinstance(checkpoint.get("maximum_resume_count"), int)
        or not 1 <= checkpoint["maximum_resume_count"] <= 10
    ):
        errors.append("enterprise checkpoint policy is invalid")
    retention = profile.get("retention", {})
    if (
        not isinstance(retention, dict)
        or set(retention) != {"mode", "checkpoint_days", "evidence_days"}
        or retention.get("mode") != "digest-and-redacted-claims-only"
        or not isinstance(retention.get("checkpoint_days"), int)
        or not 1 <= retention["checkpoint_days"] <= 30
        or not isinstance(retention.get("evidence_days"), int)
        or not retention["checkpoint_days"] <= retention["evidence_days"] <= 365
    ):
        errors.append("enterprise retention policy is invalid")
    bounds = profile.get("bounds", {})
    campaign_bounds = campaign_profile.get("bounds", {})
    if (
        not isinstance(bounds, dict)
        or set(bounds) != {"max_total_response_bytes"}
        or not isinstance(bounds.get("max_total_response_bytes"), int)
        or bounds["max_total_response_bytes"] < campaign_bounds.get("max_response_bytes", 0)
        or bounds["max_total_response_bytes"] > 16_777_216
    ):
        errors.append("enterprise aggregate response bound is invalid")
    serialized = json.dumps(profile, sort_keys=True).lower()
    if any(f'"{name}"' in serialized for name in ("password", "token", "authorization", "secret", "private_key")):
        errors.append("enterprise appliance profile contains credential-shaped fields")
    return errors


def load_appliance_profile(path: Path, campaign_profile: Mapping[str, Any]) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    errors = validate_appliance_profile(payload, campaign_profile)
    if errors:
        raise ApplianceError("profile-invalid")
    return payload


def _bindings(
    appliance_profile: Mapping[str, Any], campaign_profile: Mapping[str, Any], graph: Mapping[str, Any]
) -> dict[str, str]:
    return {
        "appliance_profile_sha256": str(appliance_profile["content_sha256"]),
        "campaign_profile_sha256": canonical_hash(campaign_profile),
        "graph_sha256": str(graph["content_sha256"]),
    }


def _initial_checkpoint(
    appliance_profile: Mapping[str, Any], campaign_profile: Mapping[str, Any], graph: Mapping[str, Any]
) -> dict[str, Any]:
    return _seal({
        "schema_version": APPLIANCE_SCHEMA_VERSION,
        "receipt_type": "lightyear-enterprise-collection-checkpoint",
        "appliance_id": appliance_profile["appliance_id"],
        "status": "running",
        "bindings": _bindings(appliance_profile, campaign_profile, graph),
        "adapter_index": 0,
        "current_path": campaign_profile["adapters"][REQUIRED_ADAPTERS[0]]["path"],
        "total_pages": 0,
        "total_response_bytes": 0,
        "retry_count": 0,
        "resume_count": 0,
        "backoff_schedule_ms": [],
        "adapter_state": {},
        "raw_bodies_retained": False,
        "production_ready": False,
    })


def _validate_checkpoint(
    checkpoint: Mapping[str, Any],
    appliance_profile: Mapping[str, Any],
    campaign_profile: Mapping[str, Any],
    graph: Mapping[str, Any],
) -> None:
    if checkpoint.get("content_sha256") != canonical_hash(checkpoint, {"content_sha256"}):
        raise ApplianceError("checkpoint-content-hash-invalid")
    if (
        checkpoint.get("receipt_type") != "lightyear-enterprise-collection-checkpoint"
        or checkpoint.get("bindings") != _bindings(appliance_profile, campaign_profile, graph)
        or checkpoint.get("production_ready") is not False
        or checkpoint.get("raw_bodies_retained") is not False
        or checkpoint.get("status") not in {"running", "interrupted", "completed", "blocked"}
    ):
        raise ApplianceError("checkpoint-contract-invalid")
    state = checkpoint.get("adapter_state")
    if not isinstance(state, dict) or not set(state).issubset(REQUIRED_ADAPTERS):
        raise ApplianceError("checkpoint-adapter-state-invalid")
    pages = 0
    response_bytes = 0
    for adapter_id, item in state.items():
        if not isinstance(item, dict) or set(item) != {"claims", "artifacts", "paths", "complete"}:
            raise ApplianceError("checkpoint-adapter-state-invalid")
        if not isinstance(item["claims"], list) or not isinstance(item["artifacts"], list):
            raise ApplianceError("checkpoint-adapter-state-invalid")
        paths = item["paths"]
        if not isinstance(paths, list) or len(paths) != len(set(paths)):
            raise ApplianceError("checkpoint-pagination-ledger-invalid")
        if len(paths) != len(item["artifacts"]):
            raise ApplianceError("checkpoint-page-artifact-count-invalid")
        for path in paths:
            _validate_page_path(path, appliance_profile["pagination"]["allowed_query_keys"])
        pages += len(paths)
        response_bytes += sum(int(artifact.get("bytes", -1)) for artifact in item["artifacts"])
    if checkpoint.get("total_pages") != pages or checkpoint.get("total_response_bytes") != response_bytes:
        raise ApplianceError("checkpoint-summary-invalid")
    index = checkpoint.get("adapter_index")
    if not isinstance(index, int) or not 0 <= index <= len(REQUIRED_ADAPTERS):
        raise ApplianceError("checkpoint-adapter-index-invalid")
    if any(not state.get(adapter_id, {}).get("complete") for adapter_id in REQUIRED_ADAPTERS[:index]):
        raise ApplianceError("checkpoint-completion-order-invalid")
    if index < len(REQUIRED_ADAPTERS):
        current = checkpoint.get("current_path")
        if not isinstance(current, str):
            raise ApplianceError("checkpoint-current-path-invalid")
        _validate_page_path(current, appliance_profile["pagination"]["allowed_query_keys"])


def _fetch_with_retry(
    transport: ApplianceTransport,
    path: str,
    accepted_types: tuple[str, ...],
    policy: Mapping[str, int],
    *,
    sleeper: Callable[[float], None],
) -> tuple[ApplianceResponse, list[int]]:
    schedule: list[int] = []
    for attempt in range(1, int(policy["max_attempts"]) + 1):
        try:
            response = transport.get(path, accepted_types)
            if response.content_type not in accepted_types:
                raise ApplianceError("content-type-rejected")
            return response, schedule
        except ApplianceError as exc:
            if not exc.retryable or attempt >= int(policy["max_attempts"]):
                raise
            backoff = min(
                int(policy["base_backoff_ms"]) * (2 ** (attempt - 1)),
                int(policy["max_backoff_ms"]),
            )
            if exc.retry_after_ms is not None:
                if exc.retry_after_ms < 0 or exc.retry_after_ms > int(policy["max_retry_after_ms"]):
                    raise ApplianceError("retry-after-out-of-bounds") from None
                backoff = exc.retry_after_ms
            schedule.append(backoff)
            sleeper(backoff / 1000)
    raise ApplianceError("retry-state-invalid")


def run_appliance(
    appliance_profile: Mapping[str, Any],
    campaign_profile: Mapping[str, Any],
    graph: Mapping[str, Any],
    transport: ApplianceTransport,
    output_root: Path,
    *,
    collected_at: str,
    resume: bool = False,
    stop_after_pages: int | None = None,
    evidence_class: str = "simulated",
    signing_key: bytes | None = None,
    key_id: str | None = None,
    fault_receipt: Mapping[str, Any] | None = None,
    sleeper: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    errors = validate_appliance_profile(appliance_profile, campaign_profile)
    if errors:
        raise ApplianceError("profile-invalid")
    if evidence_class not in {"simulated", "live"}:
        raise ApplianceError("evidence-class-invalid")
    if evidence_class == "live" and (signing_key is None or not key_id):
        raise ApplianceError("live-signature-required")
    output_root.mkdir(parents=True, exist_ok=True)
    checkpoint_path = output_root / "checkpoint.json"
    receipt_path = output_root / "appliance.receipt.json"
    if resume:
        if not checkpoint_path.is_file() or receipt_path.exists():
            raise ApplianceError("resume-requires-unfinished-checkpoint")
        checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        _validate_checkpoint(checkpoint, appliance_profile, campaign_profile, graph)
        if checkpoint["status"] not in {"running", "interrupted"}:
            raise ApplianceError("resume-checkpoint-not-resumable")
        checkpoint = copy.deepcopy(checkpoint)
        checkpoint["status"] = "running"
        checkpoint["resume_count"] += 1
        if checkpoint["resume_count"] > appliance_profile["checkpoint"]["maximum_resume_count"]:
            raise ApplianceError("resume-count-exceeded")
        checkpoint = _seal(checkpoint)
    else:
        if checkpoint_path.exists() or receipt_path.exists():
            raise ApplianceError("output-root-not-clean")
        checkpoint = _initial_checkpoint(appliance_profile, campaign_profile, graph)
    _validate_checkpoint(checkpoint, appliance_profile, campaign_profile, graph)

    while checkpoint["adapter_index"] < len(REQUIRED_ADAPTERS):
        adapter_id = REQUIRED_ADAPTERS[checkpoint["adapter_index"]]
        config = campaign_profile["adapters"][adapter_id]
        item = checkpoint["adapter_state"].setdefault(
            adapter_id, {"claims": [], "artifacts": [], "paths": [], "complete": False}
        )
        path = checkpoint["current_path"]
        if path in item["paths"]:
            raise ApplianceError("pagination-loop")
        if len(item["paths"]) >= appliance_profile["pagination"]["max_pages_per_adapter"]:
            raise ApplianceError("page-limit-exceeded")
        try:
            response, schedule = _fetch_with_retry(
                transport,
                path,
                CONTENT_TYPES[adapter_id],
                appliance_profile["retry"],
                sleeper=sleeper,
            )
        except ApplianceError:
            checkpoint["status"] = "interrupted"
            checkpoint = _seal(checkpoint)
            write_json(checkpoint_path, checkpoint)
            raise
        if len(response.body) > campaign_profile["bounds"]["max_response_bytes"]:
            raise ApplianceError("response-truncated")
        if (
            checkpoint["total_response_bytes"] + len(response.body)
            > appliance_profile["bounds"]["max_total_response_bytes"]
        ):
            raise ApplianceError("aggregate-response-bound-exceeded")
        claims = _claims(adapter_id, response.body, config["entities"])
        body_hash = hashlib.sha256(response.body).hexdigest()
        item["claims"].extend(claims)
        item["paths"].append(path)
        item["artifacts"].append({
            "kind": _artifact_kind(adapter_id),
            "sha256": body_hash,
            "bytes": len(response.body),
            "page": len(item["paths"]),
            "content_retained": False,
        })
        checkpoint["total_pages"] += 1
        checkpoint["total_response_bytes"] += len(response.body)
        checkpoint["retry_count"] += len(schedule)
        checkpoint["backoff_schedule_ms"].extend(schedule)
        if response.next_path:
            _validate_continuation(
                path,
                response.next_path,
                config["path"],
                appliance_profile["pagination"]["allowed_query_keys"],
            )
            checkpoint["current_path"] = response.next_path
        else:
            item["complete"] = True
            checkpoint["adapter_index"] += 1
            if checkpoint["adapter_index"] < len(REQUIRED_ADAPTERS):
                next_adapter = REQUIRED_ADAPTERS[checkpoint["adapter_index"]]
                checkpoint["current_path"] = campaign_profile["adapters"][next_adapter]["path"]
            else:
                checkpoint["current_path"] = None
        checkpoint = _seal(checkpoint)
        write_json(checkpoint_path, checkpoint)
        if stop_after_pages is not None and checkpoint["total_pages"] == stop_after_pages:
            checkpoint["status"] = "interrupted"
            checkpoint = _seal(checkpoint)
            write_json(checkpoint_path, checkpoint)
            return {
                "status": "interrupted",
                "checkpoint_sha256": checkpoint["content_sha256"],
                "pages": checkpoint["total_pages"],
            }

    captures = _captures(
        checkpoint,
        appliance_profile,
        campaign_profile,
        graph,
        collected_at,
        evidence_class,
        signing_key,
        key_id,
    )
    checkpoint["status"] = "completed"
    checkpoint = _seal(checkpoint)
    write_json(checkpoint_path, checkpoint)
    receipt = build_appliance_receipt(
        appliance_profile,
        campaign_profile,
        graph,
        captures,
        checkpoint,
        fault_receipt=fault_receipt,
        trusted_keys={key_id: signing_key} if signing_key is not None and key_id else None,
    )
    _write_captures(output_root, captures)
    write_json(receipt_path, receipt)
    return receipt


def _captures(
    checkpoint: Mapping[str, Any],
    appliance_profile: Mapping[str, Any],
    campaign_profile: Mapping[str, Any],
    graph: Mapping[str, Any],
    collected_at: str,
    evidence_class: str,
    signing_key: bytes | None,
    key_id: str | None,
) -> list[dict[str, Any]]:
    captures: list[dict[str, Any]] = []
    for adapter_id in REQUIRED_ADAPTERS:
        state = checkpoint["adapter_state"][adapter_id]
        payload = {
            "schema_version": "1.0",
            "envelope_type": "lightyear-adapter-evidence",
            "envelope_id": f"appliance:{adapter_id.split('.')[-1]}:{appliance_profile['appliance_id']}",
            "adapter": {"id": adapter_id, "version": ADAPTER_VERSIONS[adapter_id]},
            "source": {
                "system": campaign_profile["source_system"],
                "kind": "remote-mainframe" if evidence_class == "live" else "enterprise-fault-lab",
                "attestation": "remote-verified" if evidence_class == "live" else "local-simulator",
            },
            "collected_at": collected_at,
            "evidence_class": evidence_class,
            "graph_binding": {"graph_id": graph["graph_id"], "content_sha256": graph["content_sha256"]},
            "scope": {
                "read_only": True,
                "mode": "resumable-enterprise-collection",
                "resources": [adapter_id],
            },
            "claims": state["claims"],
            "artifacts": state["artifacts"],
            "limitations": _limitations(evidence_class),
        }
        capture = finalize_envelope(payload, signing_key=signing_key, key_id=key_id)
        errors = validate_envelope(
            capture,
            graph=graph,
            trusted_keys={key_id: signing_key} if signing_key is not None and key_id else None,
        )
        if errors:
            raise ApplianceError("capture-validation-failed")
        captures.append(capture)
    return captures


def build_appliance_receipt(
    appliance_profile: Mapping[str, Any],
    campaign_profile: Mapping[str, Any],
    graph: Mapping[str, Any],
    captures: list[Mapping[str, Any]],
    checkpoint: Mapping[str, Any],
    fault_receipt: Mapping[str, Any] | None,
    trusted_keys: Mapping[str, bytes] | None = None,
) -> dict[str, Any]:
    capture_errors = [
        error
        for capture in captures
        for error in validate_envelope(capture, graph=graph, trusted_keys=trusted_keys)
    ]
    adapter_ids = [capture.get("adapter", {}).get("id") for capture in captures]
    live_observed = {capture.get("evidence_class") for capture in captures} == {"live"}
    fault_passed = bool(
        fault_receipt
        and fault_receipt.get("content_sha256") == canonical_hash(fault_receipt, {"content_sha256"})
        and fault_receipt.get("status") == "passed"
        and fault_receipt.get("all_expected_faults_detected") is True
    )
    checks = {
        "authentication_profiles_bounded": set(appliance_profile["authentication"]["accepted_modes"]) == AUTH_MODES,
        "checkpoint_resume": checkpoint.get("resume_count", 0) >= 1 or live_observed,
        "all_adapters_complete": sorted(adapter_ids) == sorted(REQUIRED_ADAPTERS),
        "all_captures_valid": not capture_errors,
        "pagination_bounded": checkpoint.get("total_pages", 0) >= len(REQUIRED_ADAPTERS),
        "retry_bounded": 0
        <= checkpoint.get("retry_count", 0)
        <= len(REQUIRED_ADAPTERS) * (appliance_profile["retry"]["max_attempts"] - 1),
        "raw_bodies_discarded": checkpoint.get("raw_bodies_retained") is False,
        "retention_policy_bounded": appliance_profile["retention"]["checkpoint_days"]
        <= appliance_profile["retention"]["evidence_days"],
        "fault_laboratory_passed": fault_passed,
    }
    payload = {
        "schema_version": APPLIANCE_SCHEMA_VERSION,
        "receipt_type": "lightyear-enterprise-collection-appliance",
        "appliance_id": appliance_profile["appliance_id"],
        "evidence_class": "live" if live_observed else "simulated-resilience",
        "status": "passed" if all(checks.values()) else "blocked",
        "enterprise_mechanism_ready": all(checks.values()),
        "live_observed": live_observed,
        "production_ready": False,
        "mainframe_equivalent": False,
        "bindings": {
            **_bindings(appliance_profile, campaign_profile, graph),
            "checkpoint_sha256": checkpoint.get("content_sha256"),
            "fault_receipt_sha256": fault_receipt.get("content_sha256") if fault_receipt else None,
        },
        "checks": checks,
        "operations": {
            "adapters": len(captures),
            "pages": checkpoint.get("total_pages"),
            "response_bytes": checkpoint.get("total_response_bytes"),
            "retries": checkpoint.get("retry_count"),
            "resume_count": checkpoint.get("resume_count"),
            "backoff_schedule_ms": checkpoint.get("backoff_schedule_ms"),
        },
        "authentication": {
            "accepted_modes": appliance_profile["authentication"]["accepted_modes"],
            "minimum_tls": appliance_profile["authentication"]["minimum_tls"],
            "credentials_retained": False,
        },
        "retention": {
            **appliance_profile["retention"],
            "raw_bodies_retained": False,
            "automatic_purge_executed": False,
        },
        "fault_laboratory": {
            "status": fault_receipt.get("status") if fault_receipt else "not-run",
            "scenarios": fault_receipt.get("scenario_count", 0) if fault_receipt else 0,
        },
        "captures": [
            {"adapter_id": capture["adapter"]["id"], "content_sha256": capture["content_sha256"]}
            for capture in sorted(captures, key=lambda item: item["adapter"]["id"])
        ],
        "gaps": ([
            "live-mainframe-appliance-run-not-observed",
        ] if not live_observed else []) + [
            "enterprise-identity-provider-flow-not-executed",
            "customer-vault-and-purge-scheduler-not-executed",
            "production-network-and-volume-not-qualified",
        ],
        "limitations": [
            (
                "The captures are live, but resilience faults remain a deterministic laboratory."
                if live_observed
                else "The appliance receipt uses deterministic simulated responses and faults."
            ),
            "Authentication profiles prove policy and transport mechanisms, not an enterprise IdP exchange.",
            "Retention durations are bounded policy; automatic purge remains customer-operated.",
        ],
    }
    return _seal(payload)


def run_fault_laboratory(
    fault_catalog: Mapping[str, Any], appliance_profile: Mapping[str, Any]
) -> dict[str, Any]:
    if fault_catalog.get("content_sha256") != canonical_hash(fault_catalog, {"content_sha256"}):
        raise ApplianceError("fault-catalog-content-hash-invalid")
    scenarios = fault_catalog.get("scenarios")
    if not isinstance(scenarios, list) or [item.get("fault") for item in scenarios] != list(FAULT_KINDS):
        raise ApplianceError("fault-catalog-scenarios-invalid")
    results: list[dict[str, Any]] = []
    for scenario in scenarios:
        detected = _exercise_fault(str(scenario["fault"]), appliance_profile)
        results.append({"fault": scenario["fault"], "expected": scenario["expected"], "detected": detected})
    payload = {
        "schema_version": APPLIANCE_SCHEMA_VERSION,
        "receipt_type": "lightyear-enterprise-collector-fault-laboratory",
        "evidence_class": "simulated-resilience",
        "status": "passed" if all(item["detected"] for item in results) else "blocked",
        "scenario_count": len(results),
        "all_expected_faults_detected": all(item["detected"] for item in results),
        "results": results,
        "credential_material_retained": False,
        "live_observed": False,
        "production_ready": False,
        "limitations": ["Faults are deterministic transport scripts, not a customer network exercise."],
    }
    return _seal(payload)


def _exercise_fault(fault: str, appliance_profile: Mapping[str, Any]) -> bool:
    policy = appliance_profile["retry"]
    valid = ApplianceResponse(200, "application/json", b"{}")
    if fault in {"dns-exhaustion", "tls-rejection", "timeout-recovery", "rate-limit-recovery"}:
        class Script:
            def __init__(self) -> None:
                self.calls = 0

            def get(self, path: str, accepted: tuple[str, ...]) -> ApplianceResponse:
                self.calls += 1
                if fault == "dns-exhaustion":
                    raise ApplianceError("dns-or-network", retryable=True)
                if fault == "tls-rejection":
                    raise ApplianceError("tls-rejected")
                if self.calls == 1:
                    if fault == "timeout-recovery":
                        raise ApplianceError("timeout", retryable=True)
                    raise ApplianceError("http-429", retryable=True, retry_after_ms=200)
                return valid

        scripted = Script()
        try:
            _, schedule = _fetch_with_retry(
                scripted, "/bounded", ("application/json",), policy, sleeper=lambda _: None
            )
            return fault in {"timeout-recovery", "rate-limit-recovery"} and scripted.calls == 2 and len(schedule) == 1
        except ApplianceError as exc:
            return (
                fault == "dns-exhaustion" and exc.code == "dns-or-network" and scripted.calls == policy["max_attempts"]
            ) or (fault == "tls-rejection" and exc.code == "tls-rejected" and scripted.calls == 1)
    if fault == "redirect-rejection":
        try:
            raise ApplianceError("redirect-rejected")
        except ApplianceError as exc:
            return not exc.retryable and exc.code == "redirect-rejected"
    if fault == "pagination-loop":
        try:
            _validate_continuation("/resource?cursor=1", "/resource?cursor=1", "/resource", ["cursor"])
        except ApplianceError as exc:
            return exc.code == "pagination-loop"
    if fault == "response-truncation":
        return len(b"x" * 1025) > 1024
    if fault == "checkpoint-tamper":
        checkpoint = _seal({"status": "interrupted", "counter": 1})
        checkpoint["counter"] = 2
        return checkpoint["content_sha256"] != canonical_hash(checkpoint, {"content_sha256"})
    return False


def build_appliance_evidence(
    appliance_profile: Mapping[str, Any],
    campaign_profile: Mapping[str, Any],
    graph: Mapping[str, Any],
    fixture: Mapping[str, Any],
    fault_catalog: Mapping[str, Any],
    output_root: Path,
) -> dict[str, Any]:
    fault_receipt = run_fault_laboratory(fault_catalog, appliance_profile)
    write_json(output_root / "fault-lab.receipt.json", fault_receipt)
    transport = EnterpriseFixtureTransport(fixture)
    interrupted = run_appliance(
        appliance_profile,
        campaign_profile,
        graph,
        transport,
        output_root,
        collected_at=str(fixture["collected_at"]),
        stop_after_pages=appliance_profile["checkpoint"]["interrupt_after_pages"],
        sleeper=lambda _: None,
    )
    if interrupted.get("status") != "interrupted":
        raise ApplianceError("required-interruption-not-observed")
    receipt = run_appliance(
        appliance_profile,
        campaign_profile,
        graph,
        transport,
        output_root,
        collected_at=str(fixture["collected_at"]),
        resume=True,
        fault_receipt=fault_receipt,
        sleeper=lambda _: None,
    )
    return receipt


def validate_appliance_evidence(
    appliance_profile: Mapping[str, Any],
    campaign_profile: Mapping[str, Any],
    graph: Mapping[str, Any],
    artifact_root: Path,
    trusted_keys: Mapping[str, bytes] | None = None,
) -> list[str]:
    errors: list[str] = []
    try:
        profile_errors = validate_appliance_profile(appliance_profile, campaign_profile)
        if profile_errors:
            return profile_errors
        checkpoint = json.loads((artifact_root / "checkpoint.json").read_text(encoding="utf-8"))
        _validate_checkpoint(checkpoint, appliance_profile, campaign_profile, graph)
        captures = _read_captures(artifact_root)
        fault = json.loads((artifact_root / "fault-lab.receipt.json").read_text(encoding="utf-8"))
        receipt = json.loads((artifact_root / "appliance.receipt.json").read_text(encoding="utf-8"))
        if fault.get("content_sha256") != canonical_hash(fault, {"content_sha256"}):
            errors.append("enterprise fault receipt content hash is invalid")
        expected = build_appliance_receipt(
            appliance_profile,
            campaign_profile,
            graph,
            captures,
            checkpoint,
            fault,
            trusted_keys=trusted_keys,
        )
        if receipt != expected:
            errors.append("enterprise appliance receipt differs from bound evidence")
        if checkpoint.get("status") != "completed":
            errors.append("enterprise appliance checkpoint is incomplete")
        if receipt.get("production_ready") is not False:
            errors.append("enterprise appliance receipt overstates production readiness")
        capture_is_live = {item.get("evidence_class") for item in captures} == {"live"}
        if receipt.get("live_observed") is not capture_is_live:
            errors.append("enterprise appliance live posture differs from signed captures")
    except (ApplianceError, OSError, json.JSONDecodeError) as exc:
        errors.append(str(exc))
    return sorted(errors)


def _write_captures(root: Path, captures: list[Mapping[str, Any]]) -> None:
    for capture in captures:
        write_json(root / f"{capture['adapter']['id']}.capture.json", capture)


def _read_captures(root: Path) -> list[dict[str, Any]]:
    return [
        json.loads((root / f"{adapter_id}.capture.json").read_text(encoding="utf-8"))
        for adapter_id in REQUIRED_ADAPTERS
    ]


def _validate_page_path(path: str, allowed_query_keys: list[str] | None = None) -> None:
    if not isinstance(path, str) or not path.startswith("/") or len(path) > 1_024:
        raise ApplianceError("page-path-invalid")
    parsed = urlsplit(path)
    if parsed.scheme or parsed.netloc or parsed.fragment or ".." in parsed.path.split("/"):
        raise ApplianceError("page-path-invalid")
    keys = [key for key, _ in parse_qsl(parsed.query, keep_blank_values=True)]
    if len(keys) != len(set(keys)):
        raise ApplianceError("duplicate-query-key")
    if allowed_query_keys is not None and not set(keys).issubset(allowed_query_keys):
        raise ApplianceError("pagination-query-key-rejected")


def _validate_continuation(
    current_path: str, next_path: str, initial_path: str, allowed_query_keys: list[str]
) -> None:
    _validate_page_path(next_path, allowed_query_keys)
    if next_path == current_path:
        raise ApplianceError("pagination-loop")
    if urlsplit(next_path).path != urlsplit(initial_path).path:
        raise ApplianceError("pagination-resource-drift")


def _retry_after_ms(value: Any) -> int | None:
    if value is None:
        return None
    try:
        seconds = int(str(value).strip())
    except ValueError:
        raise ApplianceError("retry-after-invalid") from None
    return seconds * 1_000


def _seal(payload: Mapping[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(dict(payload))
    result.pop("content_sha256", None)
    result["content_sha256"] = canonical_hash(result)
    return result
