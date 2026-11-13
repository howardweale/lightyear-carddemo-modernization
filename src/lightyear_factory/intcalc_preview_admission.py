"""Preview-only admission primitives. No provider, credential creation or CLI wiring."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import hashlib
import hmac
import json
import math
import os
import re
import stat
import sys
from typing import Callable, Protocol

try:
    import fcntl
except ImportError:  # Windows use-store admission is refused below.
    fcntl = None

POLICY_SHA256 = "9367543ccecbb8ac624959368c7f14b3fd2ca9329ddd6e55cd6ef23b83e9ddf7"
BUDGET_POLICY_SHA256 = "ff9e778369876d5e36bae724035ae58a80bb95e337091593d2bb23d7c6df0edd"
FEEDBACK_SHA256 = "5f94ac7bd1e0539e6682f4a70a023d20336e7b99f67d184c4f05b753c8a1531d"
FEEDBACK_LIMIT_SHA256 = "1799e9eb6fb74e2a60cb884f512a5150560298627496b9f15db3d4a24f97ec80"
SCHEMA = "full-intcalc-preview-admission/1"
ISSUER = "lightyear-full-intcalc-preview"
DOMAIN = (ISSUER + "\x00" + SCHEMA + "\x00").encode("ascii")
BINDING_FIELDS = frozenset((
    "work_order_sha256", "controller_source_manifest_sha256", "C1_gate_manifest_sha256",
    "runtime_image_digest", "build_toolchain_digest", "model_context_sha256",
    "model_allowlist_sha256", "case_manifest_sha256", "model_snapshot_sha256",
    "budget_policy_sha256", "preview_policy_sha256", "issued_at", "nonce",
    "operator_approval_sha256", "admission_expires_at", "run_budget_seconds",
    "byte_policy_sha256", "feedback_schema_sha256", "named_feedback_limit_sha256",
))


class PreviewAdmissionError(ValueError):
    """Fixed public reason only; never include an envelope, credential or path."""


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise PreviewAdmissionError(reason)


def _hash(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def _pairs(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        _require(key not in result, "duplicate-field")
        result[key] = value
    return result


def _timestamp(value: object) -> datetime:
    _require(isinstance(value, str), "invalid-timestamp")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise PreviewAdmissionError("invalid-timestamp") from None
    _require(result.tzinfo is not None and result.utcoffset() is not None,
             "timestamp-offset-required")
    return result


def _bindings(value: object) -> dict:
    _require(type(value) is dict and set(value) == BINDING_FIELDS, "binding-fields")
    for name, item in value.items():
        if name.endswith("_sha256"):
            _require((name == "byte_policy_sha256" and item == "STRICT") or _hash(item),
                     "invalid-binding-digest")
        elif name.endswith("_digest"):
            _require(isinstance(item, str) and item.startswith("sha256:")
                     and _hash(item[7:]), "invalid-runtime-digest")
    _require(value["preview_policy_sha256"] == POLICY_SHA256, "policy-mismatch")
    _require(value["budget_policy_sha256"] == BUDGET_POLICY_SHA256, "budget-policy-mismatch")
    _require(value["feedback_schema_sha256"] == FEEDBACK_SHA256, "feedback-mismatch")
    _require(value["named_feedback_limit_sha256"] == FEEDBACK_LIMIT_SHA256,
             "feedback-limit-mismatch")
    _require(type(value["run_budget_seconds"]) is int
             and value["run_budget_seconds"] == 8100, "run-budget-mismatch")
    _require(_hash(value["nonce"]), "invalid-nonce")
    issued = _timestamp(value["issued_at"])
    expiry = _timestamp(value["admission_expires_at"])
    _require(expiry - issued == timedelta(seconds=1800), "admission-validity-mismatch")
    return value


def _persist(descriptor: int) -> None:
    """Request full device synchronization where supported; never downgrade an error."""
    if fcntl is not None and hasattr(fcntl, "F_FULLFSYNC"):
        fcntl.fcntl(descriptor, fcntl.F_FULLFSYNC)
    else:
        if sys.platform == "darwin":
            raise OSError("full-sync-unavailable")
        os.fsync(descriptor)


def _reject_float(value: str) -> None:
    raise PreviewAdmissionError("float-json-forbidden")


class PreviewUseStore(Protocol):
    def consume(self, credential_id: str, nonce_sha256: str) -> None:
        """Durably consume the credential once, before any external side effect."""


class ExclusivePreviewUseStore:
    """POSIX-only ledger in a pre-provisioned owner-only controller directory.

    The trusted operator must retain this directory and credential designation
    across restarts. No constructor creates directories or searches for keys.
    A partial write remains consumed. Windows admission requires a separately
    reviewed durable store and is refused by this implementation.
    """

    def __init__(self, directory: str) -> None:
        self.directory = directory

    def consume(self, credential_id: str, nonce_sha256: str) -> None:
        _require(os.name == "posix", "unsupported-use-store-platform")
        _require(isinstance(credential_id, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,80}", credential_id)
                 is not None and _hash(nonce_sha256), "invalid-use-identity")
        directory_fd = None
        descriptor = None
        try:
            directory_fd = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            info = os.fstat(directory_fd)
            _require(info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) == 0o700,
                     "use-store-owner-mode")
            name = hashlib.sha256(credential_id.encode("ascii")).hexdigest() + ".used"
            descriptor = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                 0o600, dir_fd=directory_fd)
            data = _canonical({"schema": "full-intcalc-preview-use/1",
                               "nonce_sha256": nonce_sha256}) + b"\n"
            _require(os.write(descriptor, data) == len(data), "use-store-short-write")
            _persist(descriptor)
            _persist(directory_fd)
        except FileExistsError:
            raise PreviewAdmissionError("credential-already-consumed") from None
        except OSError:
            raise PreviewAdmissionError("use-store-unavailable-or-uncertain") from None
        finally:
            if descriptor is not None:
                os.close(descriptor)
            if directory_fd is not None:
                os.close(directory_fd)


@dataclass(frozen=True)
class PreviewAdmission:
    """Public, preview-only token. Never a production controller receipt."""
    envelope_sha256: str
    binding_sha256: str
    nonce_sha256: str
    admitted_at: str
    started_monotonic: float
    deadline_monotonic: float

    def remaining(self, monotonic_now: float) -> float:
        _require(type(monotonic_now) in (int, float) and math.isfinite(monotonic_now)
                 and monotonic_now >= self.started_monotonic, "monotonic-clock-invalid")
        return max(0.0, self.deadline_monotonic - monotonic_now)

    def public_receipt(self) -> dict:
        return {"schema": "full-intcalc-preview-result/1", "scope": "NOT-P5/public-CBACT04C-only",
                "qualified": False, "production_controller_receipt": False,
                "status": "ADMITTED_ONLY", "envelope_sha256": self.envelope_sha256,
                "binding_sha256": self.binding_sha256, "nonce_sha256": self.nonce_sha256,
                "admitted_at": self.admitted_at, "run_budget_seconds": 8100,
                "budget_policy_sha256": BUDGET_POLICY_SHA256,
                "no_resume": True, "no_retry": True, "model_calls": 0}


def admit_preview(raw: bytes, *, approved_bindings: dict, credential_id: str,
                  verification_key: bytes, use_store: PreviewUseStore,
                  wall_now: Callable[[], datetime], monotonic_now: Callable[[], float]) -> PreviewAdmission:
    """Validate exact operator bindings, verify HMAC, then consume one-use admission.

    Trusted controller supplies the approval, credential, durable store and clocks.
    This function cannot designate the operator, establish OS isolation or launch
    anything. Composition must not call it until those prerequisites are qualified.
    No signing helper or credential discovery is provided.
    """
    _require(type(raw) is bytes and 0 < len(raw) <= 16384, "envelope-size")
    _require(type(verification_key) is bytes and len(verification_key) == 32, "credential-size")
    _require(isinstance(credential_id, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,80}", credential_id)
             is not None, "credential-id")
    try:
        envelope = json.loads(raw.decode("utf-8", errors="strict"), object_pairs_hook=_pairs,
                              parse_float=_reject_float,
                              parse_constant=lambda _: (_ for _ in ()).throw(PreviewAdmissionError("nonfinite-json")))
    except (UnicodeError, json.JSONDecodeError, RecursionError):
        raise PreviewAdmissionError("invalid-envelope-json") from None
    _require(type(envelope) is dict and set(envelope) == {
        "schema", "issuer_namespace", "credential_id", "scope", "qualified",
        "production_controller_receipt", "bindings", "signature"}, "envelope-fields")
    _require(envelope["schema"] == SCHEMA and envelope["issuer_namespace"] == ISSUER
             and envelope["credential_id"] == credential_id, "preview-identity-mismatch")
    _require(envelope["scope"] == "NOT-P5/public-CBACT04C-only"
             and envelope["qualified"] is False
             and envelope["production_controller_receipt"] is False, "preview-scope-mismatch")
    bindings = _bindings(envelope["bindings"])
    _bindings(approved_bindings)
    _require(_canonical(bindings) == _canonical(approved_bindings), "operator-binding-mismatch")
    signature = envelope["signature"]
    _require(type(signature) is dict and set(signature) == {"algorithm", "value"}
             and signature["algorithm"] == "HMAC-SHA256" and _hash(signature["value"]),
             "signature-format")
    unsigned = {k: v for k, v in envelope.items() if k != "signature"}
    expected = hmac.new(verification_key, DOMAIN + _canonical(unsigned), hashlib.sha256).hexdigest()
    _require(hmac.compare_digest(signature["value"], expected), "signature-invalid")
    now = wall_now()
    _require(isinstance(now, datetime) and now.tzinfo is not None and now.utcoffset() is not None,
             "wall-clock-invalid")
    _require(_timestamp(bindings["issued_at"]) <= now <= _timestamp(bindings["admission_expires_at"]),
             "outside-admission-window")
    start = monotonic_now()
    _require(type(start) in (int, float) and math.isfinite(start) and start >= 0, "monotonic-clock-invalid")
    nonce_hash = hashlib.sha256(bindings["nonce"].encode("ascii")).hexdigest()
    use_store.consume(credential_id, nonce_hash)
    result = PreviewAdmission(hashlib.sha256(raw).hexdigest(), hashlib.sha256(_canonical(bindings)).hexdigest(),
                              nonce_hash, now.isoformat(), start, start + 8100)
    _require(result.remaining(monotonic_now()) > 0, "original-deadline-reached-during-admission")
    return result
