"""Public helper-to-controller response boundary; no helper/private execution.

Expected admission, origin key and original clocks come from authenticated
controller state, never from the reply. This does not validate an admission or
qualify native custody. Journal ownership/rollback resistance requires later
native qualification. Existing journals cannot be reopened or retried.
"""
import base64
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
from threading import RLock

from cryptography.exceptions import InvalidSignature
from lightyear_control_tower.decisions import canonical
from .external_signing import _hex, _json, _pem, SigningRefused
from .helper_route_contract import HelperRouteExchange, HelperRouteRefused, MAX_PACKET
from .helper_route_provenance import match_helper_provenance
from .signing_handoff import _plain


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class HelperControllerResult:
    admission_sha256: str
    context_sha256: str
    request_sha256: str
    response_sha256: str
    inventory_sha256: str
    status: str = "authenticated-ciphertext-received"
    native_qualified: bool = False


class HelperControllerBridge:
    def __init__(self, journal, *, binding, admission_sha256, execution_id,
                 source_index, ciphertext_inventory, source_names, artifacts,
                 original_monotonic_deadline, owner_public_key, owner_key_sha256,
                 wall_clock=None, monotonic_clock=None):
        _hex(admission_sha256, 64)
        self._key = _pem(owner_public_key, owner_key_sha256)
        provenance = match_helper_provenance(
            source_index, ciphertext_inventory, expected_binding=binding,
            expected_execution_id=execution_id, expected_source_names=source_names,
            expected_artifacts=artifacts)
        self._exchange = HelperRouteExchange(
            binding=binding, artifacts=artifacts,
            expected_names=frozenset(row.name for row in artifacts),
            original_monotonic_deadline=original_monotonic_deadline,
            wall_clock=wall_clock, monotonic_clock=monotonic_clock)
        self._admission, self._inventory = admission_sha256, provenance.inventory_sha256
        context = canonical(dict(
            schema="helper-controller-context/1", admission_sha256=admission_sha256,
            binding=binding.document(), execution_id=execution_id,
            inventory_sha256=provenance.inventory_sha256, owner_key_sha256=owner_key_sha256,
            original_monotonic_deadline=original_monotonic_deadline))
        self._context_sha256 = _sha(context)
        self._path = Path(journal).absolute()
        self._parents = {p: _plain(p, directory=True)
                         for p in (self._path.parent, *self._path.parent.parents)}
        self._fd = os.open(self._path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        self._identity = _plain(self._path)
        self._size, self._state, self._request = 0, "new", None
        self._pid, self._lock, self._closed = os.getpid(), RLock(), False
        try:
            self._record("CREATED", context_sha256=self.context_sha256)
        except BaseException:
            self.close()
            raise

    @property
    def context_sha256(self):
        return self._context_sha256

    def _live(self):
        if (self._closed or os.getpid() != self._pid
                or _plain(self._path) != self._identity
                or any(_plain(p, directory=True) != identity for p, identity in self._parents.items())
                or os.fstat(self._fd).st_size != self._size):
            raise HelperRouteRefused("helper-controller-owner-or-journal-drift")

    def _record(self, state, **digests):
        self._live()
        raw = canonical(dict(state=state, context_sha256=self.context_sha256, **{
            k: v for k, v in digests.items() if k != "context_sha256"})) + b"\n"
        written = os.write(self._fd, raw)
        if written != len(raw):
            raise HelperRouteRefused("helper-controller-uncertain-journal-write")
        os.fsync(self._fd)
        self._size += written
        self._live()

    def export_once(self):
        with self._lock:
            if self._state != "new":
                raise HelperRouteRefused("helper-controller-no-reexport")
            self._state = "consumed"
            try:
                raw = self._exchange.export_request()
                self._record("EXPORTED", request_sha256=_sha(raw))
                self._request = raw
                self._exchange._check_clock()
                self._state = "exported"
                return raw
            except BaseException:
                self.close()
                raise

    def consume_once(self, envelope):
        with self._lock:
            if self._state != "exported":
                raise HelperRouteRefused("helper-controller-no-response-retry")
            self._state = "consumed"
            try:
                # Durable before parsing, signature checks or downstream matches.
                self._record("CONSUMED")
                packet = _json(envelope, MAX_PACKET * 2)
                if set(packet) != {"schema", "context_sha256", "request_sha256",
                                   "response_base64", "signature_base64"}:
                    raise HelperRouteRefused("helper-controller-envelope-fields")
                body = {k: v for k, v in packet.items() if k != "signature_base64"}
                if (body["schema"] != "helper-controller-response/1"
                        or body["context_sha256"] != self.context_sha256
                        or body["request_sha256"] != _sha(self._request)):
                    raise HelperRouteRefused("helper-controller-original-context")
                signature = base64.b64decode(packet["signature_base64"], validate=True)
                response = base64.b64decode(body["response_base64"], validate=True)
                if (len(signature) != 64 or base64.b64encode(signature).decode() != packet["signature_base64"]
                        or base64.b64encode(response).decode() != body["response_base64"]):
                    raise HelperRouteRefused("helper-controller-canonical-encoding")
                self._key.verify(signature, canonical(body))
                matched = self._exchange.consume_authenticated_response(response)
                self._record("MATCHED", response_sha256=matched.response_sha256)
                self._exchange._check_clock()
                return HelperControllerResult(
                    self._admission, self.context_sha256, matched.request_sha256,
                    matched.response_sha256, self._inventory)
            except (InvalidSignature, SigningRefused, ValueError, TypeError) as exc:
                self.close()
                raise HelperRouteRefused("helper-controller-response-refused") from exc
            except BaseException:
                self.close()
                raise

    def mark_delivery_uncertain(self):
        with self._lock:
            if self._state != "exported":
                raise HelperRouteRefused("helper-controller-no-delivery-retry")
            self._state = "consumed"
            try:
                self._record("UNCERTAIN")
            finally:
                self.close()

    def close(self):
        with self._lock:
            if not self._closed:
                self._closed = True
                os.close(self._fd)
