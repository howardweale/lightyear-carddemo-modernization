"""Validate the review drafts without authorizing or executing any slot."""
import hashlib
from pathlib import Path
import re
import unittest
from lightyear_calibration.contracts import read_json, verify
from tools.ms94_b06_admission import verify_inputs, EvidenceFailure

ROOT = Path(__file__).resolve().parents[1]
AREA = ROOT / 'docs/calibration/idempiere-ms94/stage-b-06/preparation/admission-review-r2'


class DraftTests(unittest.TestCase):
    def test_observer_and_prospective_reason_bindings(self):
        bindings = read_json(AREA / 'source-bindings.json'); verify(bindings)
        source = ROOT / 'factory/idempiere/b06-observer/PostingObserver.java'
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), bindings['observer_java_sha256'])
        self.assertEqual(bindings['observer_host_syntax_check']['source_sha256'], bindings['observer_java_sha256'])
        for journey in ('J2', 'J3'):
            plan = read_json(AREA / (journey.lower() + '-qualification-draft.json'))
            for slot in plan['schedule']:
                control = bindings['mutants'][journey].get(slot['control'])
                if control:
                    self.assertEqual(slot['source']['sha256'], control['sha256'])

    def test_fixed_slots_sources_images_and_no_launch_authority(self):
        for journey, count in (('j1', 55), ('j2', 41), ('j3', 39)):
            plan = read_json(AREA / (journey + '-qualification-draft.json')); verify(plan)
            self.assertEqual(plan['slot_count'], count)
            self.assertEqual([s['index'] for s in plan['schedule']], list(range(1, count + 1)))
            self.assertEqual(len({s['id'] for s in plan['schedule']}), count)
            self.assertEqual(sum(s['control'] == 'retained-reference' for s in plan['schedule']), 10)
            self.assertFalse(plan['docker_runs_authorized']); self.assertFalse(plan['measurement_authorized'])
            self.assertEqual(plan['model_calls'], 0); self.assertIsNone(plan['run_entrypoint'])
            self.assertFalse(plan['restarts_allowed']); self.assertFalse(plan['replacement_slots_allowed'])
            for value in plan['images'].values(): self.assertRegex(value, r'^sha256:[a-f0-9]{64}$')
            for slot in plan['schedule']:
                self.assertRegex(slot['source']['sha256'], r'^[a-f0-9]{64}$')
                self.assertEqual(slot['engines'], ['oracle', 'postgresql'])
                if 'fault_recipe' in slot:
                    verify(slot['fault_recipe'])
                    recipe = slot['fault_recipe']
                    if 'test_module' in recipe:
                        self.assertEqual(hashlib.sha256((ROOT / recipe['test_module']).read_bytes()).hexdigest(), recipe['test_sha256'])
            # A draft cannot be passed directly to the resource-creating adapter.
            with self.assertRaisesRegex(EvidenceFailure, 'wrong-native-plan'): verify_inputs(ROOT, plan)

    def test_materials_required_cost_account_sign_and_both_equipment_targets(self):
        plan = read_json(AREA / 'j3-qualification-draft.json')
        controls = {s['control'] for s in plan['schedule']}
        self.assertTrue({'wrong-cost', 'wrong-internal-use-account', 'wrong-count-account', 'wrong-quantity-sign'} <= controls)
        for j in ('j1', 'j2', 'j3'):
            slots = read_json(AREA / (j + '-qualification-draft.json'))['schedule']
            self.assertEqual({s['target_lane'] for s in slots if s['control'] == 'genuine-equipment-fault'}, {'oracle', 'postgresql'})

    def test_template_freeze_bytes_stay_bound(self):
        historical = read_json(ROOT / 'docs/calibration/idempiere-ms94/stage-b-06/preparation/native-adapters-r1/manifest.json')
        for path, sha in historical['template_r1_files'].items():
            self.assertEqual(hashlib.sha256((ROOT / path).read_bytes()).hexdigest(), sha)


if __name__ == '__main__': unittest.main()
