import json,os,subprocess,sys,tempfile,time,unittest
from pathlib import Path
from unittest.mock import Mock,patch
from lightyear_calibration.contracts import CalibrationError,seal,read_json
from lightyear_calibration.journey_order import save
from tools.ms94_b05_stops import fingerprints,repeated,IMMEDIATE
from tools.ms94_b05_supervisor import wait_process,terminate,HARD_SECONDS,RESERVE_SECONDS,remaining_work

class SupervisorTests(unittest.TestCase):
    def test_hard_limit_reserves_finalization(self):
        self.assertLess(HARD_SECONDS,7200);self.assertGreater(RESERVE_SECONDS,0)
    def test_completed_worker_after_deadline_is_rejected(self):
        worker=Mock();worker.poll.return_value=0
        with self.assertRaises(CalibrationError):wait_process(worker,10,poll=lambda:10)
    def test_failed_worker_is_rejected(self):
        worker=Mock();worker.poll.return_value=1
        with self.assertRaises(CalibrationError):wait_process(worker,10,poll=lambda:1)
    def test_blocked_finalization_process_is_terminated_without_models(self):
        process=subprocess.Popen([sys.executable,'-c','import time; time.sleep(90)'],start_new_session=os.name!='nt')
        try:
            with self.assertRaises(CalibrationError):wait_process(process,time.monotonic()+.3)
        finally:terminate(process)
        self.assertIsNotNone(process.poll())
    def test_missing_supervision_refuses_work(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(CalibrationError):remaining_work(Path(d),Path(d)/'trial')
    def test_supervisor_timeout_records_failure_and_runs_recovery(self):
        from tools.ms94_b05_supervisor import run_unit
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);campaign=root/'trial';campaign.mkdir()
            signer=Mock();signer.sign.side_effect=seal
            child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(90)'],start_new_session=os.name!='nt')
            try:
                with patch('tools.ms94_b05_admission.preflight_authorization'),patch('tools.ms94_b05_admission.bindings',return_value=({}, {'content_sha256':'snapshot'})),patch('tools.ms94_b05_supervisor.JourneySigner',return_value=signer),patch('tools.ms94_b05_supervisor.launch_worker',return_value=child),patch('tools.ms94_b05_supervisor.HARD_SECONDS',.4),patch('tools.ms94_b05_supervisor.RESERVE_SECONDS',.1),patch('tools.ms94_b05_supervisor.recover',return_value=[]) as recovery,patch('tools.ms94_b05_stops.notify') as notify:
                    with self.assertRaises(CalibrationError):run_unit(root,campaign,'preflight')
                    recovery.assert_called_once_with(root,campaign);self.assertTrue(notify.called)
                value=read_json(campaign/'supervision-receipt.json')
                self.assertFalse(value['completed_within_budget']);self.assertIsNotNone(value['error'])
                self.assertEqual(value['model_calls'],0);self.assertIsNotNone(child.poll())
            finally:
                if child.poll() is None:child.kill();child.wait()
    def test_only_hard_failures_stop(self):
        for s in ('invalid-provenance','void-equipment-failure','halted-controller-failure','halted-trial-deadline'):
            self.assertIn(s,IMMEDIATE)
    def test_candidate_exceptions_do_not_trigger_shared_origin_stop(self):
        d={'category':'candidate-runtime-exception','thrown_by':'candidate','exception':'NullPointerException'}
        self.assertEqual(fingerprints({'status':'execution-failure'},[d]),[])
    def test_application_origin_is_unresolved_and_matching_requires_review(self):
        d={'category':'candidate-runtime-exception','thrown_by':'application','exception':'IllegalArgumentException'}
        one=fingerprints({'status':'execution-failure'},[d]);self.assertTrue(one)
        self.assertEqual(repeated(one,[{'trial_directory':'old','fingerprints':one}],'new'),one)
        self.assertEqual(repeated(one,[{'trial_directory':'old','fingerprints':['different']}],'new'),[])
    def test_business_reason_match_and_distinct_reason(self):
        a=fingerprints({'status':'business-failure','error':{'type':'BusinessViolation','message':'period cache binding'}},[])
        b=fingerprints({'status':'business-failure','error':{'type':'BusinessViolation','message':'different'}},[])
        self.assertTrue(repeated(a,[{'trial_directory':'old','fingerprints':a}],'new'))
        self.assertFalse(repeated(a,[{'trial_directory':'old','fingerprints':b}],'new'))
    def test_two_lanes_in_one_run_do_not_count_twice(self):
        d={'category':'candidate-runtime-exception','thrown_by':'application','exception':'X'}
        one=fingerprints({'status':'execution-failure'},[d,d])
        self.assertEqual(len(one),1);self.assertFalse(repeated(one,[],'new'))

if __name__=='__main__':unittest.main()
