import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from lightyear_calibration.contracts import read_json,seal,CalibrationError
from lightyear_calibration.journey_order import save
from lightyear_control_tower.decisions import verify_envelope
from tests.test_ms94_a3_entry_v2 import test_signer
from tools.ms94_dated_controls import CONTROLS,control,dated,ADDITION,assess
from tools.ms94_diagnostic_controls_v7 import AREA as OLD_AREA
from tools.ms94_dated_qualification import schedule,run

ROOT=Path(__file__).resolve().parents[1]


class DatedSourcesTests(unittest.TestCase):
    def test_exact_delta_and_support_preserved_for_every_source(self):
        for name in CONTROLS:
            with self.subTest(name=name):
                source,manifest=control(ROOT,name)
                before=(ROOT/manifest['prior_source']).read_bytes();after=source.read_bytes()
                self.assertEqual(after.replace(ADDITION.encode(),b'',1),before)
                self.assertEqual(after.count(ADDITION.encode()),1)
                self.assertEqual(after.split(b'final class JourneySupport {',1)[1],before.split(b'final class JourneySupport {',1)[1])
                self.assertFalse(manifest['prior_qualification_applies_to_this_source'])
                self.assertLess(after.index(b'order.setDateAcct(businessDate)'),after.index(b'order.saveEx()'))

    def test_runtime_frames_move_to_exact_new_throwing_line(self):
        for name in CONTROLS[1:]:
            source,new=control(ROOT,name);old=read_json(ROOT/OLD_AREA/name/'manifest.json')
            expected=copy.deepcopy(old['expected'])
            if 'candidate_frame' in expected:
                line=expected['candidate_frame']['line']
                expected['candidate_frame']['line']+=1
                before=(ROOT/old_source(name)).read_text(encoding='utf-8').splitlines()
                after=source.read_text(encoding='utf-8').splitlines()
                self.assertEqual(before[line-1],after[line])
            self.assertEqual(new['expected'],expected)

    def test_correction_rejects_duplicate_or_missing_anchor(self):
        for text in ('', 'order.setDateAcct(businessDate);',
                     '            order.setDateOrdered(businessDate);\n'*2):
            with self.assertRaises(CalibrationError):dated(text)

    def test_schedule_has_ten_reference_then_three_each_fault(self):
        slots=schedule();self.assertEqual(len(slots),28)
        self.assertEqual([s['fault'] for s in slots[:10]],['retained-reference']*10)
        for i,name in enumerate(CONTROLS[1:]):
            self.assertEqual(slots[10+i*3:13+i*3],[{'fault':name,'checkpoint_profile':'admitted','repeat':r} for r in (1,2,3)])

    def test_reference_still_requires_complete_pass_and_empty_diagnostics(self):
        _,manifest=control(ROOT,'retained-reference')
        self.assertTrue(assess({'status':'passed'},[],False,manifest))
        for status,diagnostics,suspect in [('business-failure',[],False),('passed',[{}],False),('passed',[],True)]:
            self.assertFalse(assess({'status':status},diagnostics,suspect,manifest))


def old_source(name):return OLD_AREA/name/'LightyearOperationsTest.java'


class DatedControllerBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.out=self.root/'campaign';self.signer=test_signer()
        plan=seal({'schedule':schedule(),'maximum_pairs':28,'max_elapsed_seconds':28800,'model_calls':0})
        save(self.out/'plan.json',plan)
        for name in ('authorization.json','declaration.json'):
            save(self.out/name,self.signer.sign({'plan_sha256':plan['content_sha256'],'explicit_user_authorization':True}))
        self.calls=[];self.fail_at=None;self.replay_ok=True
        def native(root,trial,*,fault,checkpoint_profile,equipment_plan,remaining_seconds):
            self.calls.append(fault);index=len(self.calls);native=root/f'run-{index}';native.mkdir()
            save(trial/'run.json',{'run_directory':native.name})
            return {'status':'passed' if fault=='retained-reference' else 'execution-failure',
                    'qualification_check_passed':index!=self.fail_at,'cleanup_complete':True,'content_sha256':str(index)}
        def replay(*args):
            return {'verified':True,'full_entry_replayed':self.replay_ok,
                    'complete_gate_replayed':True,'diagnostic_replayed':True}
        for target,value in [('tools.ms94_dated_qualification.guard',lambda root:None),
                ('tools.ms94_dated_qualification.JourneySigner',lambda root:self.signer),
                ('tools.ms94_dated_native.qualify',native),
                ('tools.ms94_a3_publication.publish',lambda *args:{'content_sha256':'publication'}),
                ('tools.ms94_a3_publication.replay',replay)]:
            mock=patch(target,value);mock.start();self.addCleanup(mock.stop)

    def test_all_slots_and_signed_terminal_without_a3_credit(self):
        report=run(self.root,self.out)
        self.assertTrue(report['passed']);self.assertEqual(len(self.calls),28)
        self.assertTrue(verify_envelope(report,self.signer.public))
        self.assertFalse(report['a3_value_invariance_qualified']);self.assertFalse(report['b04_admitted'])
        with self.assertRaises(FileExistsError):run(self.root,self.out)
        self.assertEqual(len(self.calls),28)

    def test_unexpected_result_stops_and_preserves_unstarted_slots(self):
        self.fail_at=2;report=run(self.root,self.out)
        self.assertFalse(report['passed']);self.assertEqual(len(self.calls),2)
        self.assertEqual(report['unstarted_slots'],26)
        self.assertTrue((self.out/'stopping.json').exists())
        self.assertTrue(report['results'][1]['publication_verified'])

    def test_incomplete_entry_replay_cannot_qualify_or_continue(self):
        self.replay_ok=False;report=run(self.root,self.out)
        self.assertFalse(report['passed']);self.assertEqual(len(self.calls),1)
        self.assertEqual(report['unstarted_slots'],27)
        self.assertFalse(report['results'][0]['publication_verified'])

    def test_authorization_tamper_prevents_any_native_execution(self):
        value=read_json(self.out/'authorization.json');value['plan_sha256']='wrong'
        save(self.out/'authorization.json',value)
        with self.assertRaises(CalibrationError):run(self.root,self.out)
        self.assertEqual(self.calls,[]);self.assertFalse((self.out/'started.json').exists())
