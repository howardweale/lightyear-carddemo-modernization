"""Public-reply CandidateHistory adapter; no private signer or launch wiring.

The caller owns the attended transport and independently authenticated designation
and current revocation state. This adapter is deliberately ineligible for a
production factory receipt until separate controller/native integration review.
"""
import base64
import hashlib
import json
import os
from threading import RLock

from .external_signing import SigningRefused, candidate_message, verify_candidate_reply
from .signing_designation import handoff_parameters
from .signing_handoff import PublicSigningHandoff


class CandidateHumanSigner:
    """One exact history, original binding/window, one durable public handoff."""

    def __init__(self, path, *, binding, window, attempt_identity_sha256,
                 designation, designation_sha256, designation_id,
                 current_revocations, exchange_public_reply):
        if not callable(current_revocations) or not callable(exchange_public_reply):
            raise SigningRefused("candidate-public-boundary-required")
        self._binding, self._window = binding, window
        self._designation = designation
        self._designation_sha256, self._designation_id = designation_sha256, designation_id
        self._revocations, self._exchange = current_revocations, exchange_public_reply
        self._parameters = self._check_designation()
        self._handoff = PublicSigningHandoff(
            path, binding=binding, window=window,
            attempt_identity_sha256=attempt_identity_sha256, **self._parameters)
        self._lock, self._pid = RLock(), os.getpid()
        self._used, self._failed, self._history, self._verified = False, False, None, None

    def _check_designation(self):
        return handoff_parameters(
            self._designation, expected_sha256=self._designation_sha256,
            expected_designation_id=self._designation_id, binding=self._binding,
            revoked_raw_key_sha256=self._revocations())

    def _live(self):
        if self._failed or os.getpid() != self._pid:
            raise SigningRefused("candidate-owner-unavailable-no-resume")
        self._window.check(self._binding)
        if self._check_designation() != self._parameters:
            raise SigningRefused("candidate-designation-drift")

    def expected_message(self, message):
        self._live()
        return candidate_message(message, self._binding,
                                 self._parameters["candidate_key_sha256"])

    def sign(self, history, tree, parent, message):
        with self._lock:
            if self._used:
                raise SigningRefused("candidate-attempt-already-consumed")
            self._used = True
            try:
                self._live()
                if (history.run_id != self._binding.run_id
                        or not message.startswith(
                            ("Factory candidate attempt %d\n" % self._binding.attempt).encode())):
                    raise SigningRefused("candidate-original-attempt-mismatch")
                self._history = history
                unsigned_id = history._git(
                    "commit-tree", "--no-gpg-sign", tree, "-p", parent,
                    data=message).decode().strip()
                unsigned = history._git("cat-file", "commit", unsigned_id)
                headers, actual = unsigned.split(b"\n\n", 1)
                if (headers.split(b"\n")[:2] != [
                        ("tree " + tree).encode(), ("parent " + parent).encode()]
                        or actual != message):
                    raise SigningRefused("candidate-history-exact-bytes")
                request = self._handoff.request_candidate(unsigned)
                payload = base64.b64decode(json.loads(request)["payload_base64"], validate=True)
                if payload != headers + b"\n\n" + self.expected_message(message):
                    raise SigningRefused("candidate-request-substitution")
                # Export is durably consumed before invoking the human-owned boundary.
                reply = self._exchange(request)
                checked = self._handoff.accept_candidate(reply)
                self._live()
                if checked.purpose != "candidate-commit":
                    raise SigningRefused("candidate-reply-role")
                identity = history._git(
                    "hash-object", "-t", "commit", "-w", "--stdin", data=checked.reply).decode().strip()
                if identity != checked.verified_identity:
                    raise SigningRefused("candidate-object-identity")
                self._verified = (identity, payload, checked.reply)
                self.verify(history, identity)
                return identity
            except BaseException:
                self._failed = True
                self._handoff.close()
                raise

    def verify(self, history, commit):
        with self._lock:
            try:
                self._live()
                if (history is not self._history or self._verified is None
                        or commit != self._verified[0]):
                    raise SigningRefused("candidate-unretained-history-or-commit")
                _, payload, retained = self._verified
                current = history._git("cat-file", "commit", commit)
                if current != retained:
                    raise SigningRefused("candidate-retained-reply-drift")
                identity = verify_candidate_reply(
                    payload, current,
                    allowed_signers=self._parameters["candidate_allowed_signers"],
                    key_sha256=self._parameters["candidate_key_sha256"],
                    binding=self._binding, window=self._window)
                if identity != commit:
                    raise SigningRefused("candidate-verified-identity")
                self._live()
                return True
            except BaseException:
                self._failed = True
                raise

    def close(self):
        with self._lock:
            self._failed = True
            self._handoff.close()
