"""Offline controller faults. Fake native stages confer no qualification credit."""
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from lightyear_calibration.contracts import canonical, read_json, seal
from lightyear_calibration.journey_order import file_hash
from lightyear_calibration.journey_runtime import CONTROL
from tests.test_ms94_a3_entry_v2 import test_signer
from tools.ms94_b06_qualification_driver import execute_group, intended, preliminary, finalize


class DriverTests(unittest.TestCase):
    def test_duplicate_trace_requires_execution_failure_and_specific_replay(self):
        plan={'control':'duplicate-trace-key','expected':{'status':'rejected','equipment_suspect':True,'delivery':'empty'}}
        preliminary(plan,{'status':'execution-failure','equipment_suspect':True},{'complete':True})
        for status in ('passed','business-failure','contract-violation','equipment-failure'):
            with self.subTest(status=status),self.assertRaises(ValueError):
                preliminary(plan,{'status':status,'equipment_suspect':True},{'complete':True})
        replay={'full_entry_replayed':True,'clock_replayed':True,'native_mutation_replayed':False,'equipment_suspect':True}
        with self.assertRaisesRegex(ValueError,'specific-mutant-not-replayed'): intended(plan,{'replay':replay})

    def fixture(self, directory):
        base = Path(directory); root = base/'snapshot'; root.mkdir()
        output = base/'audit'; output.mkdir(); authority = base/'authority'
        (authority/CONTROL).mkdir(parents=True)
        signer = test_signer()
        (authority/CONTROL/'authority.public.pem').write_bytes(signer.public)
        (authority/CONTROL/'authority.key.pem').write_bytes(b'NOT A KEY; unit test only, never loaded')
        now = datetime.now(timezone.utc)
        window = {'not_before_utc': (now-timedelta(hours=1)).isoformat(),
                  'deadline_utc': (now+timedelta(hours=4)).isoformat()}
        slots = []
        for name in ('j1-001','j1-002'):
            run = root/name; run.mkdir()
            plan = seal({'slot_id':name,'journey':'J1','control':'retained-reference',
                         'expected':{'status':'passed','equipment_suspect':False},
                         'declaration':{'policy':{'max_elapsed_seconds':7190}}})
            (run/'plan.json').write_bytes(canonical(plan))
            slots.append({'id':name, 'plan_path':name+'/plan.json',
                          'plan_sha256':plan['content_sha256'], 'plan_file_sha256':file_hash(run/'plan.json')})
        group = seal({'model_calls':0,'measurement_authorized':False,'snapshot_sha256':'a'*64,
                      'docker_run_window':window,'slots':slots})
        binding = {'plan_sha256':group['content_sha256'],'snapshot_sha256':'a'*64,'public_commit':'b'*40}
        (output/'authorization.json').write_bytes(canonical(signer.sign({**binding,
            'scope':'one-zero-model-journey-qualification-group','docker_run_window':window})))
        (output/'publication.json').write_bytes(canonical(signer.sign({**binding,'public_bytes_verified':True})))
        return root, output, authority, group, signer

    def test_failures_stop_before_next_slot_and_replay_after_early_notification(self):
        for failure in ('none','native','unexpected','replay','cleanup','missing-plan'):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as tmp:
                root,out,authority,group,signer = self.fixture(tmp)
                calls=[]
                def stage(kind, root, run, directory, authority, deadline):
                    calls.append((kind,run.name))
                    if kind=='native':
                        if failure=='native': raise RuntimeError('unit native failure')
                        (run/'cleanup.json').write_bytes(canonical({'complete':failure!='cleanup'}))
                        return signer.sign({'status':'passed' if failure!='unexpected' else 'business-failure',
                                            'equipment_suspect':False})
                    if failure in ('unexpected','cleanup'):
                        self.assertTrue((out/'stopping.json').exists())
                    if failure=='replay': raise ValueError('unit replay failure')
                    return signer.sign({'replay':{'full_entry_replayed':True,'clock_replayed':True,
                        'status':'passed','equipment_suspect':False,'complete_gate_replayed':True,
                        'diagnostic_replayed':True,'observer_replayed':True}})
                if failure=='missing-plan': (root/'j1-001/plan.json').unlink()
                with patch('tools.ms94_b06_qualification_driver.verify_snapshot'), \
                     patch('tools.ms94_b06_qualification_driver.supervised', side_effect=stage), \
                     patch('tools.ms94_b06_qualification_driver.recovery'):
                    report=execute_group(root,group,out,signer,authority_root=authority)
                    self.assertEqual(failure=='none', report['passed'])
                    self.assertEqual(0, report['model_calls'])
                    if failure!='none':
                        self.assertIn('j1-002',report['unstarted'])
                        self.assertFalse(any(slot=='j1-002' for _,slot in calls))
                    if failure in ('native','replay'): self.assertEqual(['j1-001'],report['unfinalized'])
                    with self.assertRaisesRegex(ValueError,'already-attempted'):
                        execute_group(root,group,out,signer,authority_root=authority)

    def test_archive_is_replayed_from_copy_and_cleanup_checked_twice(self):
        with tempfile.TemporaryDirectory() as tmp:
            root,out,_,_,signer=self.fixture(tmp); run=root/'j1-001'
            original=(run/'plan.json').read_bytes()
            def replay(root, copy, key):
                self.assertNotEqual(copy,run)
                self.assertEqual(original,(copy/'plan.json').read_bytes())
                (copy/'gate.json').write_bytes(b'only extracted copy')
                return {'full_entry_replayed':True}
            with patch('tools.ms94_b06_qualification_driver.cleanup_check',return_value={'actual_owned_cleanup_verified':True}) as cleanup, \
                 patch('tools.ms94_b06_qualification_replay.replay_pair',side_effect=replay):
                audit=finalize(root,run,out,signer.public,signer)
                self.assertEqual(2,cleanup.call_count)
                self.assertTrue(audit['replay']['full_entry_replayed'])
                self.assertFalse((run/'gate.json').exists())
                with self.assertRaisesRegex(ValueError,'archive-already-exists'): finalize(root,run,out,signer.public,signer)

    def test_missing_replay_flag_cannot_qualify_reference(self):
        plan={'control':'retained-reference','expected':{'status':'passed'}}
        replay={'full_entry_replayed':True,'clock_replayed':True,'status':'passed',
                'complete_gate_replayed':True,'diagnostic_replayed':True,'observer_replayed':True}
        intended(plan,{'replay':replay})
        for key in ('full_entry_replayed','clock_replayed','complete_gate_replayed','diagnostic_replayed','observer_replayed'):
            with self.subTest(key=key),self.assertRaises(ValueError): intended(plan,{'replay':{**replay,key:False}})


if __name__=='__main__':unittest.main()
