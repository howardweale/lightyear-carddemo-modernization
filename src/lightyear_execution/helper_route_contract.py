"""Public transport contract for the future admitted private-helper owner.

No transport, plaintext, key access, signing, process launch or admission.
Ciphertext hashes bind opaque bytes, not authenticated decryption or native
ownership. A real owner must durably enforce attempt uniqueness and authenticate
a response before passing its public bytes to this component.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import math
import re
from threading import Lock

from lightyear_control_tower.decisions import canonical
from .external_signing import SigningRefused, _hex, _json, _time

MAX_CIPHERTEXT = 16 * 1024 * 1024
MAX_PACKET = 16 * 1024
MAX_ARTIFACTS = 32


class HelperRouteRefused(ValueError):
    """Public helper descriptor is invalid, mismatched or outside its lease."""


def _require(condition, message):
    if not condition:
        raise HelperRouteRefused(message)


def _digest(value, size=64):
    try:
        return _hex(value, size)
    except SigningRefused as exc:
        raise HelperRouteRefused("helper-route-digest") from exc


def _timestamp(value):
    try:
        return _time(value)
    except SigningRefused as exc:
        raise HelperRouteRefused("helper-route-timestamp") from exc


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _name(value):
    _require(type(value) is str and re.fullmatch(r"[a-z][a-z0-9-]{0,79}\.json", value),
             "helper-route-artifact-name")
    return value


@dataclass(frozen=True)
class HelperRouteBinding:
    source_commit: str
    attempt_identity_sha256: str
    source_index_sha256: str
    seed_commitment_sha256: str
    recipient_policy_sha256: str
    owner_designation_sha256: str
    expires_at: str

    def __post_init__(self):
        _digest(self.source_commit, 40)
        for value in (self.attempt_identity_sha256, self.source_index_sha256,
                      self.seed_commitment_sha256, self.recipient_policy_sha256,
                      self.owner_designation_sha256):
            _digest(value)
        _timestamp(self.expires_at)

    def document(self):
        return dict(source_commit=self.source_commit,
                    attempt_identity_sha256=self.attempt_identity_sha256,
                    source_index_sha256=self.source_index_sha256,
                    seed_commitment_sha256=self.seed_commitment_sha256,
                    recipient_policy_sha256=self.recipient_policy_sha256,
                    owner_designation_sha256=self.owner_designation_sha256,
                    expires_at=self.expires_at)


@dataclass(frozen=True)
class CiphertextDescriptor:
    name: str
    ciphertext_sha256: str
    ciphertext_bytes: int

    def __post_init__(self):
        _name(self.name)
        _digest(self.ciphertext_sha256)
        _require(type(self.ciphertext_bytes) is int
                 and 1 <= self.ciphertext_bytes <= MAX_CIPHERTEXT,
                 "helper-route-ciphertext-size")

    @classmethod
    def from_ciphertext(cls, name, ciphertext):
        """Hash opaque age-format bytes; header recognition is not authentication."""
        _require(type(ciphertext) is bytes
                 and 1 <= len(ciphertext) <= MAX_CIPHERTEXT
                 and ciphertext.startswith(b"age-encryption.org/v1\n"),
                 "helper-route-ciphertext-format")
        return cls(name, _sha(ciphertext), len(ciphertext))

    def document(self):
        return dict(name=self.name, ciphertext_sha256=self.ciphertext_sha256,
                    ciphertext_bytes=self.ciphertext_bytes)


@dataclass(frozen=True)
class MatchedHelperResponse:
    request_sha256: str
    response_sha256: str
    artifact_names: tuple
    # This type attests only to public correspondence, never private operation.


class HelperRouteExchange:
    """Single-use, process-local correspondence check under original deadlines.

    This is not a durable journal or ownership boundary. The future integrating
    owner must persist attempt consumption before any private-helper dispatch.
    Construction cannot authorize a new attempt or a resumed signing window.
    """

    def __init__(self, *, binding, artifacts, expected_names,
                 original_monotonic_deadline, wall_clock=None, monotonic_clock=None):
        import time
        _require(type(binding) is HelperRouteBinding, "helper-route-binding")
        _require(type(expected_names) is frozenset
                 and 1 <= len(expected_names) <= MAX_ARTIFACTS,
                 "helper-route-expected-inventory")
        for name in expected_names:
            _name(name)
        _require(type(artifacts) is tuple
                 and len(artifacts) == len(expected_names)
                 and all(type(row) is CiphertextDescriptor for row in artifacts),
                 "helper-route-artifact-inventory")
        _require(len({row.name for row in artifacts}) == len(artifacts)
                 and {row.name for row in artifacts} == expected_names,
                 "helper-route-inventory-mismatch")
        _require(sum(row.ciphertext_bytes for row in artifacts) <= MAX_CIPHERTEXT,
                 "helper-route-total-size")
        _require(type(original_monotonic_deadline) in (int, float)
                 and math.isfinite(original_monotonic_deadline),
                 "helper-route-original-deadline")
        self._binding = binding
        self._deadline = original_monotonic_deadline
        self._wall = wall_clock or (lambda: datetime.now(timezone.utc))
        self._monotonic = monotonic_clock or time.monotonic
        self._lock = Lock()
        self._exported = self._consumed = False
        self._request = canonical(dict(
            schema="helper-route-request/1", binding=binding.document(),
            artifacts=[row.document() for row in sorted(artifacts, key=lambda row: row.name)],
            operation="deliver-ciphertext-to-admitted-helper-owner",
            native_qualification=False))
        _require(len(self._request) <= MAX_PACKET, "helper-route-packet-size")
        self._check_clock()

    def _check_clock(self):
        wall, monotonic = self._wall(), self._monotonic()
        _require(isinstance(wall, datetime) and wall.tzinfo is not None
                 and wall.utcoffset() is not None
                 and type(monotonic) in (int, float) and math.isfinite(monotonic)
                 and wall < _timestamp(self._binding.expires_at)
                 and monotonic < self._deadline, "helper-route-original-window-closed")

    def export_request(self):
        with self._lock:
            _require(not self._exported and not self._consumed, "helper-route-no-reexport")
            # Consume export even if the clock check fails or owner loses output.
            self._exported = True
            try:
                self._check_clock()
            except BaseException:
                self._consumed = True
                raise
            return self._request

    def consume_authenticated_response(self, response):
        """Check already-authenticated public bytes once, even when malformed.

        Authentication is the caller's responsibility; this function does not
        verify a signature, transport peer, decryption result or owner identity.
        """
        with self._lock:
            _require(self._exported and not self._consumed, "helper-route-no-response-retry")
            self._consumed = True
            self._check_clock()
            try:
                _json(response, MAX_PACKET)
                request = _json(self._request, MAX_PACKET)
            except SigningRefused as exc:
                raise HelperRouteRefused("helper-route-response-format") from exc
            expected = dict(
                schema="helper-route-response/1", request_sha256=_sha(self._request),
                binding=self._binding.document(), artifacts=request["artifacts"],
                result="ciphertext-received")
            _require(response == canonical(expected), "helper-route-response-substitution")
            self._check_clock()
            return MatchedHelperResponse(_sha(self._request), _sha(response),
                                         tuple(row["name"] for row in request["artifacts"]))
