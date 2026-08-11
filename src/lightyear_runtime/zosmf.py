from __future__ import annotations

import base64
import hashlib
import http.client
import json
import os
import re
import ssl
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Protocol
from urllib.parse import quote, urlencode, urlsplit

from .contracts import CaptureBundle, RuntimeContractError


_SAFE_JOB = re.compile(r"^[A-Z0-9$#@?*]{1,8}$")
_SAFE_JOB_ID = re.compile(r"^[A-Z0-9]{1,8}$")
_SENSITIVE_KEY = re.compile(r"password|token|authorization|cookie|secret|credential", re.I)
_ALLOWED_JSON = {"application/json", "application/json;charset=utf-8"}
_ALLOWED_TEXT = {
    "text/plain",
    "plain/text",
    "application/octet-stream",
    "text/plain;charset=utf-8",
}


class ZosmfError(RuntimeContractError):
    """Raised when a z/OSMF request violates the adapter or transport contract."""


@dataclass(frozen=True)
class HttpResponse:
    status: int
    headers: Mapping[str, str]
    body: bytes


class Transport(Protocol):
    def get(self, path: str, *, query: Mapping[str, str] | None = None,
            headers: Mapping[str, str] | None = None) -> HttpResponse: ...


@dataclass(frozen=True)
class ZosmfCredentials:
    username: str | None = None
    password: str | None = None
    bearer_token: str | None = None

    @classmethod
    def from_env(cls) -> "ZosmfCredentials":
        token = os.environ.get("ZOSMF_BEARER_TOKEN")
        user = os.environ.get("ZOSMF_USER")
        password = os.environ.get("ZOSMF_PASSWORD")
        if token and (user or password):
            raise ZosmfError("Choose bearer-token or user/password authentication, not both")
        if bool(user) != bool(password):
            raise ZosmfError("ZOSMF_USER and ZOSMF_PASSWORD must be supplied together")
        return cls(user, password, token)

    def authorization(self) -> str | None:
        if self.bearer_token:
            return f"Bearer {self.bearer_token}"
        if self.username is not None and self.password is not None:
            value = base64.b64encode(
                f"{self.username}:{self.password}".encode("utf-8")
            ).decode("ascii")
            return f"Basic {value}"
        return None


@dataclass(frozen=True)
class ZosmfConfig:
    base_url: str
    source_alias: str
    timeout_seconds: float = 15.0
    max_response_bytes: int = 1_048_576
    allow_loopback_http: bool = False
    ca_bundle: str | None = None
    client_certificate: str | None = None
    client_key: str | None = None

    @classmethod
    def from_env(cls, base_url: str | None = None) -> "ZosmfConfig":
        resolved_url = base_url or os.environ.get("ZOSMF_BASE_URL", "")
        alias = os.environ.get("ZOSMF_SYSTEM_ALIAS", "zosmf-system")
        timeout = float(os.environ.get("ZOSMF_TIMEOUT_SECONDS", "15"))
        maximum = int(os.environ.get("ZOSMF_MAX_RESPONSE_BYTES", "1048576"))
        return cls(
            resolved_url,
            alias,
            timeout,
            maximum,
            False,
            os.environ.get("ZOSMF_CA_BUNDLE"),
            os.environ.get("ZOSMF_CLIENT_CERT"),
            os.environ.get("ZOSMF_CLIENT_KEY"),
        )

    def validate(self) -> None:
        parsed = urlsplit(self.base_url)
        if parsed.username or parsed.password:
            raise ZosmfError("Credentials are forbidden in the z/OSMF URL")
        if parsed.query or parsed.fragment or parsed.path not in {"", "/"}:
            raise ZosmfError("z/OSMF base URL must contain only scheme, host, and optional port")
        if not parsed.hostname:
            raise ZosmfError("z/OSMF base URL requires a host")
        loopback = _is_loopback(parsed.hostname)
        if parsed.scheme == "http" and not (loopback and self.allow_loopback_http):
            raise ZosmfError("HTTP is permitted only for the local simulator")
        if parsed.scheme not in {"http", "https"}:
            raise ZosmfError("z/OSMF base URL must use HTTPS")
        if self.timeout_seconds <= 0 or self.timeout_seconds > 120:
            raise ZosmfError("z/OSMF timeout must be between 0 and 120 seconds")
        if self.max_response_bytes < 1024 or self.max_response_bytes > 16 * 1024 * 1024:
            raise ZosmfError("z/OSMF response limit must be between 1 KiB and 16 MiB")
        if bool(self.client_certificate) != bool(self.client_key):
            raise ZosmfError("Client certificate and key must be supplied together")

    @property
    def is_loopback(self) -> bool:
        hostname = urlsplit(self.base_url).hostname or ""
        return _is_loopback(hostname)

    @property
    def can_attest_real_zos(self) -> bool:
        return urlsplit(self.base_url).scheme == "https" and not self.is_loopback


class HttpClientTransport:
    """Small no-redirect transport with bounded reads and verified TLS."""

    def __init__(self, config: ZosmfConfig) -> None:
        config.validate()
        self.config = config
        self.parsed = urlsplit(config.base_url)
        self.context: ssl.SSLContext | None = None
        if self.parsed.scheme == "https":
            self.context = ssl.create_default_context(cafile=config.ca_bundle)
            self.context.minimum_version = ssl.TLSVersion.TLSv1_2
            if config.client_certificate and config.client_key:
                self.context.load_cert_chain(config.client_certificate, config.client_key)

    def get(self, path: str, *, query: Mapping[str, str] | None = None,
            headers: Mapping[str, str] | None = None) -> HttpResponse:
        if not path.startswith("/zosmf/") or ".." in path or "//" in path:
            raise ZosmfError("Refusing an unsafe z/OSMF resource path")
        target = path
        if query:
            target += "?" + urlencode(query)
        connection: http.client.HTTPConnection
        if self.parsed.scheme == "https":
            connection = http.client.HTTPSConnection(
                self.parsed.hostname,
                self.parsed.port or 443,
                timeout=self.config.timeout_seconds,
                context=self.context,
            )
        else:
            connection = http.client.HTTPConnection(
                self.parsed.hostname,
                self.parsed.port or 80,
                timeout=self.config.timeout_seconds,
            )
        try:
            connection.request("GET", target, headers=dict(headers or {}))
            response = connection.getresponse()
            length = response.getheader("Content-Length")
            if length and int(length) > self.config.max_response_bytes:
                raise ZosmfError("z/OSMF response exceeds the configured byte limit")
            body = response.read(self.config.max_response_bytes + 1)
            if len(body) > self.config.max_response_bytes:
                raise ZosmfError("z/OSMF response exceeds the configured byte limit")
            return HttpResponse(
                response.status,
                {key.lower(): value for key, value in response.getheaders()},
                body,
            )
        except (OSError, http.client.HTTPException) as error:
            raise ZosmfError(f"z/OSMF connection failed: {type(error).__name__}") from error
        finally:
            connection.close()


class ZosmfClient:
    def __init__(self, transport: Transport, credentials: ZosmfCredentials) -> None:
        self.transport = transport
        self.credentials = credentials

    def list_jobs(self, owner: str, prefix: str, max_jobs: int = 100) -> list[dict[str, Any]]:
        if not 1 <= max_jobs <= 1000:
            raise ZosmfError("max_jobs must be between 1 and 1000")
        payload = self._json(
            "/zosmf/restjobs/jobs",
            query={"owner": _job_value(owner), "prefix": _job_value(prefix),
                   "max-jobs": str(max_jobs), "exec-data": "Y"},
        )
        if not isinstance(payload, list):
            raise ZosmfError("z/OSMF job list response must be an array")
        return [_object(item, "job") for item in payload]

    def job_status(self, job_name: str, job_id: str) -> dict[str, Any]:
        payload = self._json(
            _job_path(job_name, job_id),
            query={"step-data": "Y", "exec-data": "Y"},
        )
        return _object(payload, "job status")

    def spool_files(self, job_name: str, job_id: str) -> list[dict[str, Any]]:
        payload = self._json(f"{_job_path(job_name, job_id)}/files")
        if not isinstance(payload, list):
            raise ZosmfError("z/OSMF spool-file response must be an array")
        return [_object(item, "spool file") for item in payload]

    def spool_records(self, job_name: str, job_id: str, file_id: int | str,
                      max_records: int = 5000) -> bytes:
        identifier = str(file_id)
        if identifier != "JCL" and (not identifier.isdigit() or int(identifier) < 0):
            raise ZosmfError("Invalid spool file identifier")
        response = self._get(
            f"{_job_path(job_name, job_id)}/files/{quote(identifier, safe='')}/records",
            headers={
                "Accept": "text/plain, application/octet-stream",
                "X-IBM-Record-Range": f"0,{max_records}",
            },
        )
        _content_type(response, _ALLOWED_TEXT)
        return response.body

    def _json(self, path: str, query: Mapping[str, str] | None = None) -> Any:
        response = self._get(path, query=query)
        _content_type(response, _ALLOWED_JSON)
        try:
            return json.loads(response.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ZosmfError("z/OSMF returned invalid JSON") from error

    def _get(self, path: str, query: Mapping[str, str] | None = None,
             headers: Mapping[str, str] | None = None) -> HttpResponse:
        request_headers = {"Accept": "application/json"}
        request_headers.update(headers or {})
        authorization = self.credentials.authorization()
        if authorization:
            request_headers["Authorization"] = authorization
        response = self.transport.get(path, query=query, headers=request_headers)
        if response.status < 200 or response.status >= 300:
            raise ZosmfError(f"z/OSMF request failed with HTTP {response.status}")
        return response


class ZosmfJobsAdapter:
    """Read-only JES collector that emits graph-addressed, content-minimized evidence."""

    def __init__(self, client: ZosmfClient, config: ZosmfConfig, mapping_path: Path,
                 job_name: str, job_id: str, *, attest_real_zos: bool = False) -> None:
        config.validate()
        if attest_real_zos and not config.can_attest_real_zos:
            raise ZosmfError("Real z/OS attestation requires verified HTTPS on a non-loopback host")
        self.client = client
        self.config = config
        self.mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
        self.job_name = _job_value(job_name)
        self.job_id = _job_id(job_id)
        self.evidence_class = "zos_observed" if attest_real_zos else "simulated"

    def capture(self) -> CaptureBundle:
        status = self.client.job_status(self.job_name, self.job_id)
        if status.get("jobname") != self.job_name or status.get("jobid") != self.job_id:
            raise ZosmfError("z/OSMF returned a different job identity")
        files = self.client.spool_files(self.job_name, self.job_id)
        spool_artifacts, jcl = self._collect_spool(files)
        observations = self._observations(status, jcl)
        mapping = self.mapping
        required_nodes = [mapping["job"]["node_id"]]
        required_edges: list[str] = []
        for step in mapping["steps"]:
            required_nodes.extend([step["node_id"], step["program_node_id"]])
            required_edges.extend([step["job_step_edge_id"], step["step_program_edge_id"]])
        required_edges.extend(item["edge_id"] for item in mapping["dd_allocations"])
        completed = str(status.get("exec-ended") or "").strip()
        captured_at = completed if completed else datetime.now(timezone.utc).isoformat()
        payload = {
            "run_id": f"zosmf-{self.job_name.lower()}-{self.job_id.lower()}",
            "adapter_id": "lightyear.zosmf-jobs.v1",
            "source_system": self.config.source_alias,
            "captured_at": captured_at,
            "evidence_class": self.evidence_class,
            "required_nodes": required_nodes,
            "required_edges": required_edges,
            "artifacts": spool_artifacts,
            "limitations": [
                "JES and spool evidence does not prove transactional locking or all subsystem behavior.",
                "Spool bodies are hashed and discarded; only bounded metadata and matches are retained.",
            ] + (["Local z/OSMF simulator evidence is synthetic, not mainframe evidence."]
                 if self.evidence_class == "simulated" else []),
            "observations": observations,
        }
        return CaptureBundle.from_dict(redact_payload(payload))

    def _collect_spool(self, files: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], str]:
        artifacts = []
        jcl_parts = []
        allowed = {"JESJCL", "JCL", "JESMSGLG", "JESYSMSG"}
        for item in files:
            ddname = str(item.get("ddname") or "").upper()
            if ddname not in allowed:
                continue
            file_id = item.get("id")
            if not isinstance(file_id, int):
                raise ZosmfError("Spool file id must be an integer")
            body = self.client.spool_records(self.job_name, self.job_id, file_id)
            digest = hashlib.sha256(body).hexdigest()
            artifacts.append({
                "kind": "jes-spool",
                "ddname": ddname,
                "stepname": item.get("stepname"),
                "record_count": item.get("record-count"),
                "byte_count": item.get("byte-count"),
                "sha256": digest,
                "content_retained": False,
            })
            if ddname in {"JESJCL", "JCL"}:
                jcl_parts.append(body.decode("utf-8", errors="replace"))
        return artifacts, "\n".join(jcl_parts)

    def _observations(self, status: dict[str, Any], jcl: str) -> list[dict[str, Any]]:
        mapping = self.mapping
        job_details = {
            "job_id": self.job_id,
            "status": status.get("status"),
            "return_code": status.get("retcode"),
            "exec_system": status.get("exec-system"),
            "exec_started": status.get("exec-started"),
            "exec_ended": status.get("exec-ended"),
        }
        observations = [_observation("node", mapping["job"]["node_id"],
                                     "job_completed", job_details)]
        step_data = status.get("step-data", [])
        if not isinstance(step_data, list):
            raise ZosmfError("z/OSMF step-data must be an array")
        for expected in mapping["steps"]:
            actual = next((item for item in step_data
                           if str(item.get("step-name", "")).strip() == expected["name"]), None)
            if not actual:
                continue
            program = str(actual.get("program-name", "")).strip()
            if program != expected["program"]:
                observations.append(_observation(
                    "node", expected["program_node_id"], "program_identity_mismatch",
                    {"expected": expected["program"], "actual": program}, "contradicted"))
                continue
            observations.extend([
                _observation("node", expected["node_id"], "step_completed", {
                    "step_name": expected["name"],
                    "completion_code": actual.get("completion-code"),
                }),
                _observation("node", expected["program_node_id"], "program_invoked",
                             {"program_name": program}),
                _observation("edge", expected["job_step_edge_id"], "job_step_observed",
                             {"job_name": self.job_name, "step_name": expected["name"]}),
                _observation("edge", expected["step_program_edge_id"], "step_program_observed",
                             {"step_name": expected["name"], "program_name": program}),
            ])
        upper_jcl = jcl.upper()
        for allocation in mapping["dd_allocations"]:
            ddname = allocation["ddname"].upper()
            present = re.search(rf"(?m)^//{re.escape(ddname)}\s+DD\b", upper_jcl) is not None
            if present:
                observations.append(_observation(
                    "edge", allocation["edge_id"], "dd_allocation_observed",
                    {"dd_name": ddname, "access": allocation["access"]}))
        return observations


def redact_payload(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): "[REDACTED]" if _SENSITIVE_KEY.search(str(key)) else redact_payload(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_payload(item) for item in value]
    if isinstance(value, tuple):
        return [redact_payload(item) for item in value]
    return value


def _observation(kind: str, identifier: str, operation: str, details: dict[str, Any],
                 assertion: str = "observed") -> dict[str, Any]:
    return {
        "entity_kind": kind,
        "entity_id": identifier,
        "assertion": assertion,
        "operation": operation,
        "details": details,
    }


def _job_value(value: str) -> str:
    normalized = value.upper().strip()
    if not _SAFE_JOB.fullmatch(normalized):
        raise ZosmfError("Invalid z/OS job owner, name, or prefix")
    return normalized


def _job_id(value: str) -> str:
    normalized = value.upper().strip()
    if not _SAFE_JOB_ID.fullmatch(normalized):
        raise ZosmfError("Invalid z/OS job ID")
    return normalized


def _job_path(job_name: str, job_id: str) -> str:
    return "/zosmf/restjobs/jobs/" + quote(_job_value(job_name), safe="") + "/" + quote(
        _job_id(job_id), safe=""
    )


def _content_type(response: HttpResponse, allowed: set[str]) -> None:
    content_type = response.headers.get("content-type", "").lower().replace(" ", "")
    if content_type not in allowed:
        raise ZosmfError(f"Unexpected z/OSMF content type: {content_type or 'missing'}")


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ZosmfError(f"z/OSMF {label} response must be an object")
    return value


def _is_loopback(hostname: str) -> bool:
    return hostname.lower() in {"localhost", "127.0.0.1", "::1"}
