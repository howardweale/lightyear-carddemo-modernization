"""Synthetic CI tests: metrics are observations, never admission or billing proof."""
from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from lightyear_factory.contracts import canonical_hash
from lightyear_factory.journal_metrics import (
    JournalBinding, MetricsError, collect_cases, collect_journal, write_report,
)
from tools.report_attempt_metrics import render_inventory

IDENTITY = "a" * 64
E = "b" * 40
REQUEST = "c" * 64
CASES = [f"case-{number:02}" for number in range(19)]


class Journal:
    def __init__(self, identity=IDENTITY, protocol=5):
        self.identity, self.events, self.count_events = identity, [], []
        self.add("model_reservations", protocol=protocol)

    def add(self, kind, **payload):
        event = dict(sequence=len(self.events) + 1, occurred_at="2026-01-01T00:00:00Z",
                     previous_sha256=self.events[-1]["event_sha256"] if self.events else None,
                     state="OBSERVED", kind=kind,
                     payload=dict(attempt_identity_sha256=self.identity, **payload))
        event["event_sha256"] = canonical_hash(event)
        self.events.append(event)
        return event

    def count(self, kind, **fields):
        row = dict(kind=kind, attempt_identity_sha256=self.identity,
                   event_sequence=len(self.count_events) + 1,
                   previous_count_event_sha256=(self.count_events[-1]["content_sha256"]
                                                if self.count_events else None), **fields)
        row["content_sha256"] = canonical_hash(row)
        self.count_events.append(row)
        self.add("count_financial", event=row)
        return row

    def transport(self, kind="responses", observation=None):
        sequence = 1 + sum(e["kind"] == "model_transport_reserved" for e in self.events)
        event = self.add("model_transport_reserved", transport_sequence=sequence,
                         reservation=dict(transport_kind=kind, request_sha256=REQUEST))
        ticket = dict(attempt_identity_sha256=self.identity, transport_sequence=sequence,
                      request_sha256=REQUEST, reservation_event_sha256=event["event_sha256"])
        if observation is not None:
            self.add("model_transport_observed", reservation_ticket=ticket,
                     observation=observation)
        return ticket

    def source(self):
        raw = ("\n".join(json.dumps(e) for e in self.events) + "\n").encode()
        binding = JournalBinding(CASES[0], E, "execution-1", 1, 1, self.identity,
                                 sha256(raw).hexdigest(), self.events[-1]["event_sha256"])
        return binding, raw

    def report(self):
        binding, raw = self.source()
        return collect_journal(raw, binding)


class JournalMetricsTests(unittest.TestCase):
    def test_generation_preflight_and_logical_cost_not_double_counted(self):
        journal = Journal()
        journal.add("reserved", reservation=dict(call_sequence=1, estimated_cost_usd="2"))
        journal.transport("input-token-count", dict(input_token_count=17))
        journal.transport(observation=dict(response_usage=dict(input_tokens=17, output_tokens=4),
                                           cost_estimate_available=True, estimated_cost_usd="1.25"))
        journal.add("sanitized_accounting", accounting=dict(calls=1, estimated_cost_usd="1.25"))
        report = journal.report()
        self.assertEqual(report["tokens"]["input_tokens"]["observed_subtotal"], 17)
        self.assertEqual(report["count_endpoint_estimate"]["observed_subtotal"], 17)
        self.assertEqual(report["usd"]["logical_checkpoint_conservative"], "1.25")
        self.assertEqual(report["usd"]["generation_transport_estimates"]["observed_subtotal"], "1.25")
        self.assertIsNone(report["usd"]["combined_total"])
        self.assertEqual(report["tokens"]["cached_input_tokens"]["missing_observations"], 1)
        self.assertIsNone(report["physical_sends"])

    def test_count_settlement_replaces_hold_and_unknown_retains_full_hold(self):
        for count, charge in [(None, "2"), (17, "0.25")]:
            with self.subTest(count=count):
                journal = Journal()
                reserve = journal.count("count_charge_reserved", count_sequence=1,
                                        request_sha256=REQUEST, reserved_cost_usd="2")
                ticket = dict(count_sequence=1, request_sha256=REQUEST,
                              reservation_event_sha256=reserve["content_sha256"])
                journal.count("count_charge_observed", ticket=ticket, counted_input_tokens=count,
                              conservative_charge_usd=charge, billing_final=False)
                report = journal.report()
                self.assertEqual(report["usd"]["count_conservative_exposure"], charge)
                self.assertEqual(report["usd"]["unknown_count_hold"], "2" if count is None else "0")
                self.assertFalse(report["usd"]["invoice_final"])

    def test_unknown_count_cannot_release_hold(self):
        journal = Journal()
        reserve = journal.count("count_charge_reserved", count_sequence=1,
                                request_sha256=REQUEST, reserved_cost_usd="2")
        journal.count("count_charge_observed", counted_input_tokens=None,
                      conservative_charge_usd="0", billing_final=False,
                      ticket=dict(count_sequence=1, request_sha256=REQUEST,
                                  reservation_event_sha256=reserve["content_sha256"]))
        with self.assertRaisesRegex(MetricsError, "unknown-count-release"):
            journal.report()

    def test_partial_attempt_retains_reservation_and_unknown_usage(self):
        journal = Journal()
        journal.add("reserved", reservation=dict(call_sequence=1, estimated_cost_usd="2.50"))
        journal.transport()
        report = journal.report()
        self.assertEqual(report["unresolved_transport_reservations"], 1)
        self.assertEqual(report["usd"]["pending_logical_reservation"], "2.50")
        self.assertEqual(report["tokens"]["input_tokens"]["missing_observations"], 1)
        self.assertFalse(report["tokens"]["input_tokens"]["complete_for_observed_reservations"])
        self.assertIsNone(report["elapsed_monotonic_seconds"])
        self.assertIsNone(report["human_interventions"])

    def test_refusal_before_transport_does_not_invent_calls(self):
        report = Journal().report()
        self.assertEqual(report["observed_generation_transport_reservations"], 0)
        self.assertIsNone(report["physical_sends"])
        self.assertFalse(report["production_qualification"])

    def test_duplicates_deduplicate_and_all_nineteen_cases_remain(self):
        source = Journal().source()
        report = collect_cases(CASES, E, [source, source])
        self.assertEqual(len(report["cases"]), 19)
        self.assertEqual(report["observed_attempts"], 1)
        self.assertEqual(report["cases"][1]["observability"], "UNOBSERVED")
        self.assertIsNone(report["human_interventions"])

    def test_conflicting_snapshots_or_case_bindings_are_rejected(self):
        journal = Journal()
        old = journal.source()
        journal.transport()
        with self.assertRaisesRegex(MetricsError, "conflicting-attempt"):
            collect_cases(CASES, E, [old, journal.source()])
        changed = (replace(old[0], case_id=CASES[1]), old[1])
        with self.assertRaisesRegex(MetricsError, "conflicting-attempt"):
            collect_cases(CASES, E, [old, changed])

    def test_changed_bytes_chain_and_head_are_rejected(self):
        binding, raw = Journal().source()
        with self.assertRaisesRegex(MetricsError, "source-drift"):
            collect_journal(raw + b" ", binding)
        event = json.loads(raw)
        event["state"] = "CHANGED"
        changed = (json.dumps(event) + "\n").encode()
        with self.assertRaisesRegex(MetricsError, "chain-hash"):
            collect_journal(changed, replace(binding, source_sha256=sha256(changed).hexdigest()))
        with self.assertRaisesRegex(MetricsError, "head-drift"):
            collect_journal(raw, replace(binding, journal_head_sha256="f"*64))

    def test_partial_line_and_cross_attempt_are_rejected(self):
        binding, raw = Journal().source()
        partial = raw.rstrip(b"\n")
        with self.assertRaisesRegex(MetricsError, "truncated"):
            collect_journal(partial, replace(binding, source_sha256=sha256(partial).hexdigest()))
        with self.assertRaisesRegex(MetricsError, "attempt-drift"):
            collect_journal(raw, replace(binding, attempt_identity_sha256="f"*64))

    def test_ticket_replay_or_request_substitution_is_rejected(self):
        for replay in (True, False):
            journal = Journal()
            ticket = journal.transport(observation={} if replay else None)
            if not replay:
                ticket["request_sha256"] = "f"*64
            journal.add("model_transport_observed", reservation_ticket=ticket, observation={})
            with self.assertRaisesRegex(MetricsError, "observation-ticket"):
                journal.report()

    def test_no_invented_zero_from_missing_generation_estimate(self):
        journal = Journal()
        journal.transport(observation=dict(response_usage=None, cost_estimate_available=False))
        metric = journal.report()["usd"]["generation_transport_estimates"]
        self.assertEqual(metric["missing_observations"], 1)
        self.assertFalse(metric["complete_for_observed_reservations"])

    def test_wrong_e_and_inventory_and_protocol_fail_closed(self):
        for cases in (CASES[:-1], [CASES[0]] * 19):
            with self.assertRaises(MetricsError):
                collect_cases(cases, E, [])
        with self.assertRaisesRegex(MetricsError, "inventory-binding"):
            collect_cases(CASES, "f"*40, [Journal().source()])
        with self.assertRaisesRegex(MetricsError, "protocol"):
            Journal(protocol=99).report()

    def test_nested_count_chain_drift_is_rejected(self):
        journal = Journal()
        journal.count("count_charge_reserved", count_sequence=1,
                      request_sha256=REQUEST, reserved_cost_usd="2")
        journal.events[-1]["payload"]["event"]["reserved_cost_usd"] = "0"
        journal.events[-1]["event_sha256"] = canonical_hash(journal.events[-1], {"event_sha256"})
        with self.assertRaisesRegex(MetricsError, "count-chain"):
            journal.report()

    def test_output_is_deterministic_and_never_overwrites(self):
        report = collect_cases(CASES, E, [])
        with TemporaryDirectory() as directory:
            one, two = Path(directory)/"one.json", Path(directory)/"two.json"
            self.assertEqual(write_report(one, report), write_report(two, report))
            self.assertEqual(one.read_bytes(), two.read_bytes())
            with self.assertRaises(FileExistsError):
                write_report(one, report)

    def test_inventory_adapter_uses_exact_bytes_and_does_not_touch_source(self):
        binding, raw = Journal().source()
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root/"journal.jsonl"
            source.write_bytes(raw)
            inventory = dict(schema="factory-metrics-inventory/1", case_ids=CASES, exact_e=E,
                             journals=[dict(path="journal.jsonl", binding=binding.__dict__)])
            manifest = root/"inventory.json"
            manifest.write_text(json.dumps(inventory))
            render_inventory(manifest, root/"report.json")
            self.assertEqual(source.read_bytes(), raw)
            inventory["journals"][0]["path"] = "../outside.jsonl"
            manifest.write_text(json.dumps(inventory))
            with self.assertRaisesRegex(MetricsError, "source-path"):
                render_inventory(manifest, root/"refused.json")


if __name__ == "__main__":
    unittest.main()
