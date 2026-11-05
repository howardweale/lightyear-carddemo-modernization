"""Synthetic public joins only; no provider, signer or production coverage."""
from dataclasses import replace
from hashlib import sha256
import json
import unittest

from lightyear_factory.contracts import canonical_hash
from lightyear_factory.human_metrics import encode_human_event
from lightyear_factory.journal_metrics import MetricsError
from lightyear_factory.metrics_execution_joins import (
    ExecutionReference, collect_execution_joins,
)

E = "b" * 40
CASES = [f"case-{number:02}" for number in range(19)]


def receipt(case=CASES[0], execution="execution-1", attempt="a" * 64, **changes):
    row = dict(schema="factory-metrics-execution-receipt/1", exact_e=E,
               campaign_id="campaign-1", case_id=case, execution_id=execution,
               attempt_identity_sha256=attempt)
    row.update(changes)
    raw = json.dumps(row, sort_keys=True, separators=(",", ":")).encode()
    return raw, ExecutionReference(case, execution, attempt, sha256(raw).hexdigest())


def event(identity="event-1", **changes):
    row = dict(event_id=identity, actor_id="operator-1",
               occurred_at="2026-01-01T10:00:00+00:00", campaign_id="campaign-1",
               exact_e=E, case_ids=[CASES[0]], execution_ids=["execution-1"],
               action="preparation", evidence_sha256s=[receipt()[1].receipt_sha256],
               supersedes_event_id=None)
    row.update(changes)
    return row


def stream(*rows):
    raw, previous = b"", None
    for sequence, row in enumerate(rows, 1):
        line = encode_human_event(row, sequence=sequence, previous_event_sha256=previous)
        raw += line
        previous = json.loads(line)["content_sha256"]
    return raw


def collect(raw, **changes):
    payload, ref = receipt()
    args = dict(human_source_sha256=sha256(raw).hexdigest(), exact_e=E,
                campaign_id="campaign-1", case_ids=CASES, executions=(ref,),
                receipts=(payload,), authenticate_receipt=lambda value, expected: True)
    args.update(changes)
    return collect_execution_joins(raw, **args)


class MetricsExecutionJoinsTests(unittest.TestCase):
    def test_exact_join_passes_unchanged_bytes_and_expected_reference_to_verifier(self):
        payload, ref = receipt()
        calls = []

        def verify(value, expected):
            calls.append((value, expected))
            return value == payload and expected == ref

        result = collect(stream(event()), authenticate_receipt=verify)
        self.assertEqual(calls, [(payload, ref)])
        self.assertEqual(result["observed_fully_joined_event_count"], 1)
        self.assertEqual(result["executions"][0]["observed_linked_event_ids"], ["event-1"])
        self.assertEqual(result["events"][0]["joins"][0]["attempt_identity_sha256"], "a" * 64)
        self.assertFalse(result["complete_coverage"])
        self.assertFalse(result["production_qualification"])
        self.assertFalse(result["physical_send_proven"])
        self.assertFalse(result["billing_final"])
        self.assertIsNone(result["actual_intervention_count"])
        self.assertEqual(result["content_sha256"], canonical_hash(
            {key: value for key, value in result.items() if key != "content_sha256"}))

    def test_shared_action_is_one_global_event_with_two_execution_references(self):
        first, one = receipt()
        second, two = receipt(CASES[1], "execution-2", "c" * 64)
        raw = stream(event(case_ids=CASES[:2], execution_ids=["execution-1", "execution-2"],
                           evidence_sha256s=[one.receipt_sha256, two.receipt_sha256]))
        result = collect(raw, executions=(one, two), receipts=(first, second))
        self.assertEqual(result["observed_event_count"], 1)
        self.assertEqual(result["observed_fully_joined_event_count"], 1)
        self.assertEqual([row["observed_linked_event_count"] for row in result["executions"]], [1, 1])

    def test_empty_export_never_means_zero_actual_interventions(self):
        result = collect(b"", executions=(), receipts=(), authenticate_receipt=None)
        self.assertEqual(result["observed_event_count"], 0)
        self.assertIsNone(result["actual_intervention_count"])
        self.assertFalse(result["complete_coverage"])

    def test_missing_receipt_or_digest_remains_unknown(self):
        ref = receipt()[1]
        for expected in (ref, replace(ref, receipt_sha256=None)):
            with self.subTest(expected=expected):
                result = collect(stream(event()), executions=(expected,), receipts=(),
                                 authenticate_receipt=None)
                self.assertEqual(result["observed_fully_joined_event_count"], 0)
                self.assertFalse(result["executions"][0]["receipt_verified_by_caller"])
                self.assertIsNone(result["executions"][0]["actual_intervention_count"])
                self.assertEqual(result["events"][0]["joins"][0]["status"], "unknown")

    def test_authenticated_receipt_without_event_evidence_does_not_join(self):
        result = collect(stream(event(evidence_sha256s=["f" * 64])))
        self.assertTrue(result["executions"][0]["receipt_verified_by_caller"])
        self.assertEqual(result["executions"][0]["observed_linked_event_count"], 0)
        self.assertEqual(result["observed_fully_joined_event_count"], 0)

    def test_corrections_use_only_the_effective_event(self):
        raw = stream(event(), event("event-2", supersedes_event_id="event-1",
                                    evidence_sha256s=["f" * 64]))
        result = collect(raw)
        self.assertEqual(result["observed_event_count"], 1)
        self.assertEqual(result["events"][0]["root_event_id"], "event-1")
        self.assertEqual(result["events"][0]["event_id"], "event-2")
        self.assertEqual(result["executions"][0]["observed_linked_event_ids"], [])

    def test_ambiguous_attempts_stay_unknown_but_exact_evidence_selects_one(self):
        first, one = receipt()
        second, two = receipt(attempt="d" * 64)
        raw = stream(event(evidence_sha256s=[one.receipt_sha256, two.receipt_sha256]))
        result = collect(raw, executions=(one, two), receipts=(first, second))
        self.assertEqual(result["events"][0]["joins"][0]["missing_reason"], "ambiguous-attempt")
        self.assertEqual(result["observed_fully_joined_event_count"], 0)
        exact = collect(stream(event()), executions=(one, two), receipts=(first, second))
        self.assertEqual(exact["observed_fully_joined_event_count"], 1)
        self.assertEqual([r["observed_linked_event_count"] for r in exact["executions"]], [1, 0])

    def test_uncovered_case_unknown_execution_and_no_execution_stay_unknown(self):
        for changes in (dict(case_ids=CASES[:2]), dict(execution_ids=["unknown"]),
                        dict(execution_ids=[]), dict(case_ids=[CASES[1]])):
            with self.subTest(changes=changes):
                result = collect(stream(event(**changes)))
                self.assertEqual(result["observed_fully_joined_event_count"], 0)
                self.assertFalse(result["events"][0]["all_declared_links_joined"])

    def test_hash_equality_without_authentication_is_refused(self):
        for verifier in (None, lambda *_: False, lambda *_: 1, lambda *_: "true"):
            with self.subTest(verifier=verifier):
                with self.assertRaisesRegex(MetricsError, "authenticat"):
                    collect(stream(event()), authenticate_receipt=verifier)

    def test_verifier_exception_refuses_the_whole_projection(self):
        def unavailable(*_):
            raise RuntimeError("synthetic verifier unavailable")
        with self.assertRaisesRegex(MetricsError, "authentication-failed"):
            collect(stream(event()), authenticate_receipt=unavailable)

    def test_cross_source_campaign_case_execution_attempt_and_schema_refused(self):
        mutations = [dict(exact_e="f" * 40), dict(campaign_id="other"),
                     dict(case_id=CASES[1]), dict(execution_id="other"),
                     dict(attempt_identity_sha256="f" * 64), dict(schema="other")]
        original = receipt()[1]
        for change in mutations:
            with self.subTest(change=change):
                row = json.loads(receipt()[0])
                row.update(change)
                raw = json.dumps(row).encode()
                expected = replace(original, receipt_sha256=sha256(raw).hexdigest())
                with self.assertRaisesRegex(MetricsError, "cross-binding"):
                    collect(stream(event()), executions=(expected,), receipts=(raw,))

    def test_journal_source_drift_and_chain_tamper_refused(self):
        raw = stream(event())
        with self.assertRaisesRegex(MetricsError, "source-drift"):
            collect(raw, human_source_sha256="f" * 64)
        with self.assertRaises(MetricsError):
            collect(raw.replace(b"operator-1", b"operator-2"))

    def test_duplicate_extra_or_changed_receipt_bytes_refused(self):
        raw, _ = receipt()
        for values in ((raw, raw), (raw + b" ",), (receipt(execution="extra")[0],)):
            with self.subTest(values=values):
                with self.assertRaises(MetricsError):
                    collect(stream(event()), receipts=values)

    def test_duplicate_inventory_unknown_case_and_malformed_reference_refused(self):
        ref = receipt()[1]
        inventories = [(ref, ref), (replace(ref, case_id="unknown"),),
                       (replace(ref, attempt_identity_sha256="bad"),),
                       (replace(ref, receipt_sha256="bad"),), (object(),), [ref],
                       (ref, replace(ref, attempt_identity_sha256="f" * 64))]
        for inventory in inventories:
            with self.subTest(inventory=inventory):
                with self.assertRaises(MetricsError):
                    collect(stream(event()), executions=inventory)

    def test_malformed_json_duplicate_keys_nonfinite_and_extra_fields_refused(self):
        row = json.loads(receipt()[0])
        invalid = [b"{", b"[]", b'{"schema":"a","schema":"b"}',
                   b'{"schema":NaN}', json.dumps(dict(row, private_key="forbidden")).encode()]
        for payload in invalid:
            with self.subTest(payload=payload):
                ref = replace(receipt()[1], receipt_sha256=sha256(payload).hexdigest())
                with self.assertRaises(MetricsError):
                    collect(stream(event()), executions=(ref,), receipts=(payload,))

    def test_receipt_container_and_byte_types_refused(self):
        for values in ([receipt()[0]], ("text",), (b"",), (bytearray(b"x"),)):
            with self.subTest(values=values):
                with self.assertRaises(MetricsError):
                    collect(stream(event()), receipts=values)

    def test_projection_is_deterministic_when_inventory_order_changes(self):
        first, one = receipt()
        second, two = receipt(CASES[1], "execution-2", "c" * 64)
        raw = stream(event(case_ids=CASES[:2], execution_ids=["execution-1", "execution-2"],
                           evidence_sha256s=[one.receipt_sha256, two.receipt_sha256]))
        self.assertEqual(collect(raw, executions=(one, two), receipts=(first, second)),
                         collect(raw, executions=(two, one), receipts=(second, first)))
