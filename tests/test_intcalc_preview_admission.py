"""CI-only synthetic admission tests; no provider, real credential or model call."""
import copy
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, call, patch

import lightyear_factory.intcalc_preview_admission as admission

from lightyear_factory.intcalc_preview_admission import (
    BINDING_FIELDS, DOMAIN, FEEDBACK_LIMIT_SHA256, FEEDBACK_SHA256, POLICY_SHA256,
    SCHEMA, ISSUER, ExclusivePreviewUseStore, PreviewAdmissionError, admit_preview,
)

SYNTHETIC_KEY = bytes(range(32))
ISSUED = datetime(2026, 1, 1, tzinfo=timezone.utc)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def bindings():
    b = {k: "a" * 64 for k in BINDING_FIELDS}
    b.update(runtime_image_digest="sha256:" + "a" * 64,
             build_toolchain_digest="sha256:" + "b" * 64,
             preview_policy_sha256=POLICY_SHA256, budget_policy_sha256=admission.BUDGET_POLICY_SHA256,
             feedback_schema_sha256=FEEDBACK_SHA256,
             named_feedback_limit_sha256=FEEDBACK_LIMIT_SHA256, byte_policy_sha256="STRICT",
             issued_at=ISSUED.isoformat(), admission_expires_at=(ISSUED + timedelta(seconds=1800)).isoformat(),
             nonce="c" * 64, run_budget_seconds=8100)
    return b


def envelope(b=None):
    return dict(schema=SCHEMA, issuer_namespace=ISSUER, credential_id="synthetic-ci-only",
                scope="NOT-P5/public-CBACT04C-only", qualified=False,
                production_controller_receipt=False, bindings=b or bindings())


def signed(e):
    e = copy.deepcopy(e)
    unsigned = {k: v for k, v in e.items() if k != "signature"}
    e["signature"] = {"algorithm": "HMAC-SHA256", "value": hmac.new(
        SYNTHETIC_KEY, DOMAIN + canonical(unsigned), hashlib.sha256).hexdigest()}
    return canonical(e)


class MemoryUseStore:
    def __init__(self):
        self.used = set()
        self.calls = 0

    def consume(self, credential_id, nonce_sha256):
        self.calls += 1
        if credential_id in self.used:
            raise PreviewAdmissionError("credential-already-consumed")
        self.used.add(credential_id)


class PreviewAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.store = MemoryUseStore()
        self.options = dict(approved_bindings=bindings(), credential_id="synthetic-ci-only",
                            verification_key=SYNTHETIC_KEY, use_store=self.store,
                            wall_now=lambda: ISSUED, monotonic_now=lambda: 100.0)

    def admit(self, e=None, **changes):
        return admit_preview(signed(e or envelope()), **(self.options | changes))

    def test_valid_admission_is_preview_only(self):
        result = self.admit()
        self.assertEqual(result.deadline_monotonic, 8200)
        self.assertEqual(result.remaining(200), 8000)
        self.assertIs(result.public_receipt()["qualified"], False)
        self.assertIs(result.public_receipt()["production_controller_receipt"], False)
        self.assertEqual(self.store.calls, 1)

    def test_credential_is_single_use_even_with_new_nonce(self):
        self.admit()
        b = bindings(); b["nonce"] = "d" * 64
        with self.assertRaisesRegex(PreviewAdmissionError, "already-consumed"):
            self.admit(envelope(b), approved_bindings=b)

    def test_every_binding_is_exact_operator_bound(self):
        for field in BINDING_FIELDS:
            with self.subTest(field=field):
                e = envelope(); e["bindings"][field] = "f" * 64
                with self.assertRaises(PreviewAdmissionError):
                    self.admit(e)
        self.assertEqual(self.store.calls, 0)

    def test_signature_tampering_refuses_before_consumption(self):
        e = json.loads(signed(envelope())); e["signature"]["value"] = "0" * 64
        with self.assertRaisesRegex(PreviewAdmissionError, "signature-invalid"):
            admit_preview(canonical(e), **self.options)
        self.assertEqual(self.store.calls, 0)

    def test_wrong_key_refuses(self):
        with self.assertRaisesRegex(PreviewAdmissionError, "signature-invalid"):
            self.admit(verification_key=bytes(reversed(SYNTHETIC_KEY)))

    def test_unknown_top_level_and_signature_fields_refuse(self):
        e = envelope(); e["provider"] = "automatic-fallback"
        with self.assertRaises(PreviewAdmissionError): self.admit(e)
        e = json.loads(signed(envelope())); e["signature"]["extra"] = 1
        with self.assertRaises(PreviewAdmissionError): admit_preview(canonical(e), **self.options)

    def test_missing_and_extra_bindings_refuse(self):
        for change in ("missing", "extra"):
            e = envelope()
            if change == "missing": del e["bindings"]["feedback_schema_sha256"]
            else: e["bindings"]["resume"] = True
            with self.assertRaises(PreviewAdmissionError): self.admit(e)

    def test_production_namespace_and_flags_refuse(self):
        for field, value in (("schema", "lightyear-signed-work-order"),
                             ("issuer_namespace", "production"), ("qualified", True),
                             ("production_controller_receipt", True), ("qualified", 0),
                             ("scope", "P5")):
            e = envelope(); e[field] = value
            with self.subTest(field=field), self.assertRaises(PreviewAdmissionError): self.admit(e)
        self.assertEqual(self.store.calls, 0)

    def test_future_and_expired_admission_refuse(self):
        for seconds in (-1, 1801):
            with self.assertRaisesRegex(PreviewAdmissionError, "outside-admission-window"):
                self.admit(wall_now=lambda: ISSUED + timedelta(seconds=seconds))
        self.assertEqual(self.store.calls, 0)

    def test_exact_expiry_is_allowed_by_reviewed_inclusive_policy(self):
        result = self.admit(wall_now=lambda: ISSUED + timedelta(seconds=1800))
        self.assertEqual(result.deadline_monotonic, 8200)

    def test_short_or_extended_admission_validity_refuses(self):
        for seconds in (1799, 1801):
            b = bindings(); b["admission_expires_at"] = (ISSUED + timedelta(seconds=seconds)).isoformat()
            with self.assertRaisesRegex(PreviewAdmissionError, "validity-mismatch"):
                self.admit(envelope(b), approved_bindings=b)

    def test_naive_timestamp_refuses(self):
        b = bindings(); b["issued_at"] = "2026-01-01T00:00:00"
        with self.assertRaisesRegex(PreviewAdmissionError, "offset-required"):
            self.admit(envelope(b), approved_bindings=b)

    def test_run_budget_cannot_extend_or_use_boolean(self):
        for value in (8101, True, 8100.0):
            b = bindings(); b["run_budget_seconds"] = value
            with self.assertRaisesRegex(PreviewAdmissionError,
                                        "float-json-forbidden" if type(value) is float else "run-budget-mismatch"):
                self.admit(envelope(b), approved_bindings=b)

    def test_policy_feedback_and_limit_are_pinned(self):
        for field in ("preview_policy_sha256", "feedback_schema_sha256", "named_feedback_limit_sha256"):
            b = bindings(); b[field] = "f" * 64
            with self.assertRaises(PreviewAdmissionError): self.admit(envelope(b), approved_bindings=b)

    def test_byte_policy_is_strict_or_exact_digest(self):
        b = bindings(); b["byte_policy_sha256"] = "f" * 64
        self.admit(envelope(b), approved_bindings=b)
        b["byte_policy_sha256"] = "report-only"
        with self.assertRaises(PreviewAdmissionError): self.admit(envelope(b), approved_bindings=b)

    def test_duplicate_fields_and_nonfinite_json_refuse(self):
        for raw in (b'{"schema":"one","schema":"two"}', b'{"value":NaN}'):
            with self.assertRaises(PreviewAdmissionError): admit_preview(raw, **self.options)

    def test_oversize_and_invalid_json_refuse(self):
        for raw in (b"x" * 16385, b"\xff", b"[", b"[]"):
            with self.assertRaises(PreviewAdmissionError): admit_preview(raw, **self.options)

    def test_credential_size_and_id_refuse(self):
        for options in ({"verification_key": b"x" * 31}, {"credential_id": "../wrong"}):
            with self.assertRaises(PreviewAdmissionError): self.admit(**options)

    def test_monotonic_invalid_or_rollback_refuses(self):
        for value in (-1, float("nan"), float("inf"), True):
            with self.assertRaises(PreviewAdmissionError): self.admit(monotonic_now=lambda: value)
        times = iter((100, 99))
        with self.assertRaises(PreviewAdmissionError): self.admit(monotonic_now=lambda: next(times))
        self.assertEqual(self.store.calls, 1)

    def test_slow_consumption_does_not_extend_deadline(self):
        times = iter((100, 8200))
        with self.assertRaisesRegex(PreviewAdmissionError, "original-deadline"):
            self.admit(monotonic_now=lambda: next(times))
        self.assertEqual(self.store.calls, 1)
        with self.assertRaisesRegex(PreviewAdmissionError, "already-consumed"): self.admit()

    def test_public_receipt_has_no_key_nonce_or_bindings(self):
        receipt = self.admit().public_receipt()
        self.assertNotIn("nonce", receipt)
        self.assertNotIn("bindings", receipt)
        self.assertNotIn("signature", receipt)
        self.assertNotIn(SYNTHETIC_KEY.hex(), json.dumps(receipt))

    def test_atomic_store_or_explicit_unsupported_platform(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ExclusivePreviewUseStore(directory)
            if os.name != "posix":
                with self.assertRaisesRegex(PreviewAdmissionError, "unsupported-use-store-platform"):
                    store.consume("synthetic-ci-only", "a" * 64)
                return
            os.chmod(directory, 0o700)
            def consume(_):
                try: store.consume("synthetic-ci-only", "a" * 64); return "admitted"
                except PreviewAdmissionError: return "refused"
            with ThreadPoolExecutor(max_workers=2) as pool:
                self.assertEqual(sorted(pool.map(consume, range(2))), ["admitted", "refused"])
            self.assertEqual(len(list(Path(directory).iterdir())), 1)

    def test_uncertain_persistence_stays_consumed(self):
        if os.name != "posix":
            with self.assertRaises(PreviewAdmissionError):
                ExclusivePreviewUseStore("unused-ci-path").consume("synthetic", "a" * 64)
            return
        with tempfile.TemporaryDirectory() as directory:
            os.chmod(directory, 0o700); store = ExclusivePreviewUseStore(directory)
            with patch("lightyear_factory.intcalc_preview_admission._persist", side_effect=OSError("synthetic")):
                with self.assertRaises(PreviewAdmissionError): store.consume("synthetic", "a" * 64)
            with self.assertRaisesRegex(PreviewAdmissionError, "already-consumed"):
                store.consume("synthetic", "a" * 64)

    def test_world_accessible_store_refuses(self):
        if os.name != "posix":
            with self.assertRaises(PreviewAdmissionError):
                ExclusivePreviewUseStore("unused-ci-path").consume("synthetic", "a" * 64)
            return
        with tempfile.TemporaryDirectory() as directory:
            os.chmod(directory, 0o755)
            with self.assertRaisesRegex(PreviewAdmissionError, "owner-mode"):
                ExclusivePreviewUseStore(directory).consume("synthetic", "a" * 64)

    def test_utf16_and_utf32_envelopes_refuse_before_consumption(self):
        text = signed(envelope()).decode("utf-8")
        for encoding in ("utf-16", "utf-16-le", "utf-16-be", "utf-32", "utf-32-le", "utf-32-be"):
            with self.subTest(encoding=encoding), self.assertRaisesRegex(PreviewAdmissionError, "invalid-envelope-json"):
                admit_preview(text.encode(encoding), **self.options)
        self.assertEqual(self.store.calls, 0)

    def test_all_float_literals_refuse_before_consumption(self):
        for literal in (b"0.0", b"-0.0", b"1e0", b"1e400", b"-1e400", b"1e-400"):
            raw = signed(envelope()).replace(b'"run_budget_seconds":8100', b'"run_budget_seconds":' + literal)
            with self.subTest(literal=literal), self.assertRaisesRegex(PreviewAdmissionError, "float-json-forbidden"):
                admit_preview(raw, **self.options)
        self.assertEqual(self.store.calls, 0)

    def test_fullsync_requests_file_and_directory_without_fsync(self):
        native = Mock(F_FULLFSYNC=51)
        with patch.object(admission, "fcntl", native), patch.object(admission.os, "fsync") as sync:
            admission._persist(101)
            admission._persist(102)
        self.assertEqual(native.fcntl.call_args_list, [call(101, 51), call(102, 51)])
        sync.assert_not_called()

    def test_fsync_fallback_only_when_fullsync_unavailable(self):
        for native in (None, Mock(spec=["fcntl"])):
            with patch.object(admission.sys, "platform", "linux"), patch.object(admission, "fcntl", native), patch.object(admission.os, "fsync") as sync:
                admission._persist(101)
                admission._persist(102)
                self.assertEqual(sync.call_args_list, [call(101), call(102)])

    def test_fullsync_error_never_downgrades(self):
        native = Mock(F_FULLFSYNC=51)
        native.fcntl.side_effect = OSError("synthetic fullsync failure")
        with patch.object(admission, "fcntl", native), patch.object(admission.os, "fsync") as sync:
            with self.assertRaises(OSError): admission._persist(101)
            sync.assert_not_called()

    def test_store_persists_regular_file_then_directory(self):
        if os.name != "posix":
            with self.assertRaises(PreviewAdmissionError):
                ExclusivePreviewUseStore("unused-ci-path").consume("synthetic", "a" * 64)
            return
        import stat
        modes = []
        with tempfile.TemporaryDirectory() as directory:
            os.chmod(directory, 0o700)
            with patch.object(admission, "_persist", side_effect=lambda fd: modes.append(os.fstat(fd).st_mode)):
                ExclusivePreviewUseStore(directory).consume("synthetic", "a" * 64)
        self.assertEqual(len(modes), 2)
        self.assertTrue(stat.S_ISREG(modes[0]))
        self.assertTrue(stat.S_ISDIR(modes[1]))

    def test_directory_persistence_failure_refuses_and_stays_consumed(self):
        if os.name != "posix":
            with self.assertRaises(PreviewAdmissionError):
                ExclusivePreviewUseStore("unused-ci-path").consume("synthetic", "a" * 64)
            return
        with tempfile.TemporaryDirectory() as directory:
            os.chmod(directory, 0o700)
            store = ExclusivePreviewUseStore(directory)
            with patch.object(admission, "_persist", side_effect=[None, OSError("synthetic directory failure")]):
                with self.assertRaisesRegex(PreviewAdmissionError, "unavailable-or-uncertain"):
                    store.consume("synthetic", "a" * 64)
            with self.assertRaisesRegex(PreviewAdmissionError, "already-consumed"):
                store.consume("synthetic", "a" * 64)

    def test_macos_without_fullsync_refuses_without_fsync(self):
        for native in (None, Mock(spec=["fcntl"])):
            with patch.object(admission.sys, "platform", "darwin"), patch.object(admission, "fcntl", native), patch.object(admission.os, "fsync") as sync:
                with self.assertRaisesRegex(OSError, "full-sync-unavailable"):
                    admission._persist(101)
                sync.assert_not_called()

    def test_e2_budget_policy_pinned_even_when_operator_bindings_match(self):
        b=bindings(); b["budget_policy_sha256"]="f"*64
        with self.assertRaisesRegex(PreviewAdmissionError,"budget-policy-mismatch"):
            self.admit(envelope(b),approved_bindings=b)
        self.assertEqual(self.store.calls,0)
    def test_e2_receipt_carries_exact_budget_join(self):
        result=self.admit()
        self.assertEqual(result.public_receipt()["budget_policy_sha256"],admission.BUDGET_POLICY_SHA256)
        self.assertEqual(result.deadline_monotonic,8200)
        self.assertEqual(self.store.calls,1)
    def test_e2_missing_budget_policy_refused_before_consumption(self):
        b=bindings(); del b["budget_policy_sha256"]
        with self.assertRaisesRegex(PreviewAdmissionError,"binding-fields"):
            self.admit(envelope(b),approved_bindings=b)
        self.assertEqual(self.store.calls,0)


    def test_e2_policy_file_hash_and_arithmetic(self):
        import hashlib
        raw=(Path(__file__).resolve().parents[1] / "spec/intcalc-preview/2026-11-13/ADMISSION-E2-BUDGET.json").read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),admission.BUDGET_POLICY_SHA256)
        policy=json.loads(raw)
        holds={role:2*((cap*11+1)//2)+792000 for role,cap in policy["role_input_caps"].items()}
        self.assertEqual(holds,policy["role_holds_microdollars"])
        self.assertEqual(sum(holds.values()),9458636)
        self.assertEqual(policy["envelope_microdollars"]-sum(holds.values()),1364)
