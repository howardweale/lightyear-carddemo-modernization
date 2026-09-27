"""Adversarial rules over retained evidence; mutations are test fixtures only."""
import copy
from datetime import date
from pathlib import Path
import tempfile
import unittest

from lightyear_calibration.contracts import read_json, seal
from lightyear_calibration.journey_judge_v2 import compare, exact_decimal, same_second
from tools.evaluate_journey_judge_v2 import verify_assessment

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / 'docs/calibration/idempiere-judge-v2'


def reseal(value):
    return seal({k: v for k, v in value.items() if k != 'content_sha256'})


class JudgeV2Tests(unittest.TestCase):
    def setUp(self):
        self.lanes = {l: read_json(EVIDENCE / ('native-' + l + '.json')) for l in ('oracle', 'postgresql')}
        self.effects = read_json(EVIDENCE / 'original-effects.json')
        self.original = read_json(EVIDENCE / 'original-gate.json')['comparison']
        v2 = read_json(EVIDENCE / 'comparison-v2.json')
        self.bindings = v2['shipment_bindings']
        self.context = v2['native_context']
        self.policy = read_json(EVIDENCE / 'policy.json')
        self.decision = read_json(EVIDENCE / 'timestamp-decision.json')
        self.day = date.fromisoformat(v2['assessed_on'])

    def result(self):
        return compare(self.lanes, self.effects, self.original, self.bindings,
                       self.context, self.policy, self.decision, self.day)

    def rebind(self):
        self.lanes = {l: reseal(v) for l, v in self.lanes.items()}
        self.effects = reseal(self.effects)
        self.original['lane_receipt_sha256'] = {l: v['content_sha256'] for l, v in self.lanes.items()}
        self.original['effect_checkpoint_sha256'] = self.effects['content_sha256']
        for finding in self.original['raw_trace_differences']:
            for lane in self.lanes:
                finding[lane] = self.lanes[lane]['trace'][finding['field']]
        self.original = reseal(self.original)

    def test_retained_evidence_passes_only_new_scope(self):
        value = self.result()
        self.assertTrue(value['passed'])
        self.assertFalse(value['original_bounded_partial_invoicing_equivalence'])
        self.assertEqual(2, len(value['newly_admitted_row_differences']))
        self.assertEqual(5, len(value['newly_admitted_trace_differences']))
        for field in ('application_equivalence', 'schema_equivalence', 'platform_qualification', 'independently_attested'):
            self.assertFalse(value[field])
        self.assertEqual(0, value['new_native_executions'])

    def test_decimal_is_exact_without_binary_float_or_tolerance(self):
        for a, b in [('10', '10.00'), ('3', '3.0'), ('1e-20', '.00000000000000000001')]:
            self.assertTrue(exact_decimal(a, b))
        for a, b in [('10', '10.000000000000001'), ('NaN', 'NaN'), ('Infinity', 'Infinity'), (' 3', '3'), ('3', 3)]:
            self.assertFalse(exact_decimal(a, b))

    def test_timestamp_rejects_changed_seconds_offsets_or_invalid_dates(self):
        a = '2026-09-26T12:34:56'
        self.assertTrue(same_second(a, a + '.999999'))
        for b in ('2026-09-26T12:34:57', a + 'Z', a + '+01:00', '2026-02-30T12:34:56'):
            self.assertFalse(same_second(a, b))
        self.assertFalse(same_second(a + '.1', a + '.1'))

    def test_real_numeric_difference_remains_unresolved(self):
        self.lanes['postgresql']['trace']['order.discount'] = '10.01'
        self.rebind()
        self.assertFalse(self.result()['passed'])

    def test_equal_nonfinite_numeric_value_cannot_bypass(self):
        for lane in self.lanes.values():
            lane['trace']['order.discount'] = 'NaN'
        self.rebind()
        self.assertFalse(self.result()['passed'])

    def test_unknown_numeric_field_is_not_normalized(self):
        for lane, value in [('oracle', '3'), ('postgresql', '3.0')]:
            self.lanes[lane]['trace']['other.amount'] = value
        self.original['raw_trace_differences'].append({'field': 'other.amount', 'oracle': '3', 'postgresql': '3.0', 'rule': None})
        self.rebind()
        self.assertFalse(self.result()['passed'])

    def test_unrelated_timestamp_column_remains_unresolved(self):
        finding = copy.deepcopy(self.effects['unresolved_differences'][0])
        finding['column'] = 'otherdate'
        self.effects['unresolved_differences'].append(finding)
        self.rebind()
        self.assertFalse(self.result()['passed'])

    def test_wrong_capture_timezone_is_rejected(self):
        self.context['capture_session_timezones']['postgresql'] = 'Europe/London'
        with self.assertRaises(ValueError): self.result()

    def test_wrong_native_datatype_is_rejected(self):
        self.context['oracle_datatype'] = 'TIMESTAMP(6)'
        with self.assertRaises(ValueError): self.result()

    def test_native_context_hash_must_bind_to_lane_state(self):
        self.context['state_sha256']['oracle'] = '0' * 64
        with self.assertRaises(ValueError): self.result()

    def test_trace_timestamp_must_match_the_native_row(self):
        self.bindings['shipment']['postgresql'] = '2026-09-26T12:34:56.999999'
        with self.assertRaises(ValueError): self.result()

    def test_oracle_date_cannot_hide_fractional_seconds(self):
        self.bindings['shipment']['oracle'] = '2026-09-26T12:34:56.1'
        with self.assertRaises(ValueError): self.result()

    def test_binding_cannot_point_to_another_shipment(self):
        self.bindings['shipment']['oracle_id'] = '999999'
        with self.assertRaises(ValueError): self.result()

    def test_review_date_stops_new_assessment(self):
        self.day = date.fromisoformat(self.decision['review_date'])
        with self.assertRaises(ValueError): self.result()

    def test_business_regression_is_not_accepted(self):
        self.lanes['postgresql']['status'] = 'business-readback-failed'
        self.rebind()
        with self.assertRaises(ValueError): self.result()

    def test_policy_cannot_expand_numeric_scope(self):
        self.policy['numeric_trace_fields'].append('invoice.total')
        with self.assertRaises(ValueError): self.result()

    def test_signed_publication_replays_with_original_false(self):
        result = verify_assessment(EVIDENCE)
        self.assertTrue(result['passed'])
        self.assertFalse(result['original_gate_passed'])
        self.assertFalse(result['full_native_gate_replayed'])

    def test_modified_publication_is_rejected(self):
        import shutil
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / 'assessment'
            shutil.copytree(EVIDENCE, output)
            with (output / 'comparison-v2.json').open('ab') as stream:
                stream.write(b' ')
            with self.assertRaises(ValueError): verify_assessment(output)


if __name__ == '__main__': unittest.main()
