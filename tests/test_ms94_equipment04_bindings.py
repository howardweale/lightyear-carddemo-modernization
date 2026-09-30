"""Real equipment-04 evidence and actual Stage B entry-point bindings."""
import hashlib
import unittest
from pathlib import Path

from lightyear_calibration.contracts import read_json, verify
from lightyear_calibration.journey_order import file_hash
from lightyear_control_tower.decisions import verify_envelope
from lightyear_calibration import ms94_v4_judge, qualification_observer_runtime_v4
from tools import ms94_measure_v4, ms94_controller_v4, ms94_native_b_v4, ms94_v4_gate, ms94_broker_v4
from tools.ms94_stage_b_evidence import stage_a, EQUIPMENT_HASH, ACCEPTANCE_HASH, KEY_HASH
from tools.ms94_execution_snapshot import guard

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT/'docs/calibration/idempiere-ms94/equipment-04'


class Equipment04Bindings(unittest.TestCase):
    def test_real_signed_equipment_has_62_verified_results_and_reviewed_components(self):
        plan = read_json(EVIDENCE/'plan.json'); verify(plan)
        key = (EVIDENCE/'authority.public.pem').read_bytes()
        self.assertEqual(hashlib.sha256(key).hexdigest(), KEY_HASH)
        self.assertEqual(plan['content_sha256'], EQUIPMENT_HASH)
        acceptance = read_json(EVIDENCE/'acceptance.json')
        report = read_json(EVIDENCE/'report.json')
        self.assertTrue(verify_envelope(acceptance, key))
        self.assertTrue(verify_envelope(report, key))
        self.assertEqual(acceptance['content_sha256'], ACCEPTANCE_HASH)
        self.assertEqual(acceptance['native_report_sha256'], report['content_sha256'])
        self.assertTrue(acceptance['stage_a_accepted'])
        self.assertEqual(len(plan['schedule']), 62)
        self.assertEqual(len(report['results']), 62)
        self.assertTrue(all(r['qualification_check_passed'] and r['publication_verified'] for r in report['results']))
        self.assertEqual(plan['judge_version'], 'idempiere-qualified-judge-v5-observer-ms94')
        self.assertEqual(plan['observer_version'], 'native-transaction-observer-v4')
        for name in (
            'src/lightyear_calibration/ms94_v4_judge.py',
            'src/lightyear_calibration/qualification_observer_runtime_v4.py',
            'src/lightyear_calibration/qualification_observer_v4.py',
            'tools/ms94_v4_gate.py',
            'factory/idempiere/qualification-ms94-v3/public/JourneySupport.java',
            'factory/idempiere/qualification-ms94-v3/public/operations-shapes.json',
        ):
            with self.subTest(path=name):
                self.assertEqual(file_hash(ROOT/name), plan['implementation_sha256'][name])

    def test_entry_points_call_the_qualified_judge_observer_and_reviewed_public_inputs(self):
        self.assertIs(ms94_measure_v4.controller, ms94_controller_v4)
        self.assertIs(ms94_native_b_v4.evaluate, ms94_v4_gate.evaluate)
        self.assertIs(ms94_v4_gate.judge, ms94_v4_judge.evaluate)
        self.assertIs(ms94_native_b_v4.Observer, qualification_observer_runtime_v4.Observer)
        self.assertEqual(ms94_v4_gate.VERSION, 'idempiere-qualified-judge-v5-observer-ms94')
        public = Path('factory/idempiere/qualification-ms94-v3/public')
        self.assertEqual(ms94_broker_v4.PUBLIC, public)
        self.assertEqual(ms94_controller_v4.SUPPORT, public/'JourneySupport.java')
        self.assertEqual(ms94_controller_v4.public_prompt(ROOT)['public_shapes'], read_json(ROOT/public/'operations-shapes.json'))
        self.assertEqual(ms94_controller_v4.public_prompt(ROOT)['public_trace_contract'], read_json(ROOT/public/'operations.json'))

    def test_real_local_execution_snapshot_loads_complete_equipment_without_hash_substitution(self):
        snapshot = ROOT/'work/ms94/execution-snapshots/stage-b-02'
        if not snapshot.exists(): self.skipTest('local execution snapshot required; portable signed evidence tested separately')
        manifest = guard(snapshot)
        equipment, accepted = stage_a(snapshot, snapshot/'docs/calibration/idempiere-ms94/equipment-04')
        self.assertEqual(manifest['qualified_equipment_plan_sha256'], equipment['content_sha256'])
        self.assertEqual(len(equipment['implementation_sha256']), 488)
        self.assertTrue(accepted['passed'])
        cohort = read_json(snapshot/'work/ms94/stage-b-02/plan.json'); verify(cohort)
        self.assertEqual(len(cohort['slots']), 13)
        for slot in cohort['slots']:
            trial = ms94_controller_v4.frozen(snapshot, snapshot/slot['path'])
            self.assertEqual(trial['content_sha256'], slot['plan_sha256'])
            self.assertEqual(trial['judge_version'], equipment['judge_version'])
            self.assertEqual(trial['equipment_plan_sha256'], equipment['content_sha256'])
            self.assertEqual(trial['support_sha256'], equipment['implementation_sha256'][ms94_controller_v4.SUPPORT.as_posix()])


if __name__ == '__main__': unittest.main()
