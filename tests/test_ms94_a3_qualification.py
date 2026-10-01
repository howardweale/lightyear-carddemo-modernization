import copy
from pathlib import Path
import unittest
from lightyear_calibration.contracts import read_json
from lightyear_calibration.journey_order import file_hash
from tools.ms94_a3_controls import control,equal_projections,assess,CONTROLS
from tools.ms94_a3_qualification import schedule
from tools.ms94_diagnostic_controls_v7 import FAULTS,AREA


class PairedCheckpointTests(unittest.TestCase):
    def projection(self):
        return {'diagnostics':[{'category':'candidate-runtime-exception','exception_class':'AssertionError',
             'candidate_frame':{'method':'run','line':5},'lanes':'both'}],
             'equipment_suspect':False,'disposition':'qualified-control','diagnostic_bytes_sha256':'not-trusted-for-equality'}

    def test_actual_bytes_must_match_even_when_claimed_hashes_match(self):
        left=self.projection();right=copy.deepcopy(left)
        self.assertTrue(equal_projections(left,right))
        right['diagnostics'][0]['private_amount']='123.45'
        self.assertFalse(equal_projections(left,right))

    def test_origin_or_stage_or_candidate_frame_drift_fails(self):
        for name,value in (('public_stage','invoice'),('thrown_by','application'),('candidate_frame',{'method':'other','line':6})):
            left=self.projection();right=copy.deepcopy(left);right['diagnostics'][0][name]=value
            self.assertFalse(equal_projections(left,right))

    def test_support_disposition_cannot_be_hidden_by_empty_feedback(self):
        left={'diagnostics':[],'equipment_suspect':True,'disposition':'halted-equipment-suspect'}
        right={**left,'equipment_suspect':False}
        self.assertFalse(equal_projections(left,right))
        right={**left,'disposition':'qualified-control'}
        self.assertFalse(equal_projections(left,right))

    def test_schedule_has_exactly_one_base_and_derived_run_per_control(self):
        slots=schedule();self.assertEqual(len(slots),14)
        self.assertEqual(CONTROLS[0],'retained-reference')
        self.assertEqual(set(CONTROLS[1:]),set(FAULTS))
        for n,name in enumerate(CONTROLS):
            self.assertEqual(slots[2*n:2*n+2],[{'fault':name,'checkpoint_profile':p} for p in ('admitted','perturbed')])

    def test_sources_are_the_existing_frozen_control_sources(self):
        root=Path(__file__).resolve().parents[1]
        for name in FAULTS:
            source,manifest=control(root,name)
            self.assertEqual(source,root/AREA/name/'LightyearOperationsTest.java')
            self.assertEqual(file_hash(source),manifest['harness_sha256'])
        source,manifest=control(root,'retained-reference')
        self.assertEqual(manifest['harness_sha256'],read_json(source.parent/'manifest.json')['harness_sha256'])

    def test_retained_path_check_requires_clean_business_pass(self):
        manifest={'fault':'retained-reference'}
        self.assertTrue(assess({'status':'passed'},[],False,manifest))
        for status in ('business-failure','execution-failure','contract-violation','judge-error','insufficient-evidence'):
            self.assertFalse(assess({'status':status},[],False,manifest))
        self.assertFalse(assess({'status':'passed'},[{'unexpected':True}],False,manifest))


if __name__=='__main__':unittest.main()
