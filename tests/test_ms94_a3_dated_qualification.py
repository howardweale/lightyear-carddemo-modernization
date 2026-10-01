import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from lightyear_calibration.contracts import read_json,seal,CalibrationError
from lightyear_calibration.journey_order import save
from lightyear_control_tower.decisions import verify_envelope
from tests.test_ms94_a3_entry_v2 import test_signer
from tools.ms94_dated_controls import CONTROLS,control
from tools.ms94_a3_dated_qualification import schedule,run


class DatedPairBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.out=self.root/'campaign';self.signer=test_signer()
        plan=seal({'schedule':schedule(),'maximum_pairs':14,'max_elapsed_seconds':28800,'model_calls':0})
        save(self.out/'plan.json',plan)
        for name in ('authorization.json','declaration.json'):
            save(self.out/name,self.signer.sign({'plan_sha256':plan['content_sha256'],'explicit_user_authorization':True}))
        self.calls=[];self.fail_at=None;self.cleanup_ok=True;self.replay_ok=True;self.drift=None;self.tamper=False
        def native(root,trial,*,fault,checkpoint_profile,equipment_plan,remaining_seconds):
            self.calls.append((fault,checkpoint_profile));index=len(self.calls);folder=root/f'run-{index}';folder.mkdir()
            save(trial/'run.json',{'run_directory':folder.name})
            projection={'diagnostics':[],'equipment_suspect':fault=='support-throw',
                        'disposition':'halted-equipment-suspect' if fault=='support-throw' else 'qualified-control',
                        'diagnostic_bytes_sha256':'same-untrusted-hash'}
            if checkpoint_profile=='perturbed' and self.drift:
                projection.update(self.drift)
            projection=self.signer.sign(projection)
            if self.tamper:projection['equipment_suspect']=not projection['equipment_suspect']
            save(folder/'diagnostic-projection.json',projection)
            return {'status':'passed' if fault=='retained-reference' else 'execution-failure',
                    'qualification_check_passed':index!=self.fail_at,'cleanup_complete':self.cleanup_ok,'content_sha256':str(index)}
        def replay(*args):
            return {'verified':True,'full_entry_replayed':self.replay_ok,'complete_gate_replayed':True,'diagnostic_replayed':True}
        for target,value in [('tools.ms94_a3_dated_qualification.guard',lambda root:None),
                ('tools.ms94_a3_dated_qualification.JourneySigner',lambda root:self.signer),
                ('tools.ms94_dated_native.qualify',native),
                ('tools.ms94_a3_publication.publish',lambda *args:{'content_sha256':'publication'}),
                ('tools.ms94_a3_publication.replay',replay)]:
            mocked=patch(target,value);mocked.start();self.addCleanup(mocked.stop)

    def test_exact_schedule_sources_and_completed_signed_comparisons(self):
        self.assertEqual(schedule(),[{'fault':f,'checkpoint_profile':p} for f in CONTROLS for p in ('admitted','perturbed')])
        source_root=Path(__file__).resolve().parents[1]
        for f in CONTROLS:
            source,manifest=control(source_root,f)
            self.assertIn('dated-controls',source.parts)
            self.assertFalse(manifest['prior_qualification_applies_to_this_source'])
        report=run(self.root,self.out)
        self.assertTrue(report['passed']);self.assertEqual(len(report['comparisons']),7)
        self.assertTrue(verify_envelope(report,self.signer.public));self.assertFalse(report['b04_admitted'])
        with self.assertRaises(FileExistsError):run(self.root,self.out)
        self.assertEqual(len(self.calls),14)

    def test_unexpected_reference_stops_before_faults(self):
        self.fail_at=2;report=run(self.root,self.out)
        self.assertFalse(report['passed']);self.assertEqual(len(self.calls),2)
        self.assertEqual(report['unstarted_slots'],12);self.assertTrue((self.out/'stopping.json').exists())
        self.assertTrue(report['results'][-1]['publication_verified'])

    def test_actual_diagnostic_bytes_override_same_claimed_digest(self):
        self.drift={'diagnostics':[{'category':'unexpected'}]};report=run(self.root,self.out)
        self.assertFalse(report['passed']);self.assertEqual(len(self.calls),2)
        self.assertFalse(report['comparisons'][0]['diagnostic_bytes_equal'])

    def test_empty_feedback_suspicion_difference_stops(self):
        self.drift={'equipment_suspect':True};report=run(self.root,self.out)
        self.assertFalse(report['passed']);self.assertEqual(len(self.calls),2)

    def test_empty_feedback_disposition_difference_stops(self):
        self.drift={'disposition':'halted-equipment-suspect'};report=run(self.root,self.out)
        self.assertFalse(report['passed']);self.assertEqual(len(self.calls),2)

    def test_invalid_projection_signature_stops(self):
        self.tamper=True;report=run(self.root,self.out)
        self.assertFalse(report['passed']);self.assertEqual(len(self.calls),2)
        self.assertIsNotNone(report['error'])

    def test_missing_full_entry_replay_cannot_qualify(self):
        self.replay_ok=False;report=run(self.root,self.out)
        self.assertFalse(report['passed']);self.assertEqual(len(self.calls),1)
        self.assertFalse(report['results'][0]['publication_verified'])

    def test_cleanup_failure_stops(self):
        self.cleanup_ok=False;report=run(self.root,self.out)
        self.assertFalse(report['passed']);self.assertEqual(len(self.calls),1)

    def test_changed_authorization_blocks_any_execution(self):
        value=read_json(self.out/'authorization.json');value['plan_sha256']='wrong';save(self.out/'authorization.json',value)
        with self.assertRaises(CalibrationError):run(self.root,self.out)
        self.assertEqual(self.calls,[])
