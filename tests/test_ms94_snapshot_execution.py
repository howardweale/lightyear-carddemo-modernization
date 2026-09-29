import tempfile,unittest
from pathlib import Path
from tools.ms94_equipment_v3 import schedule
from tools.ms94_v3_gate import evaluate
from lightyear_calibration.journey_order import save,RUNS
from lightyear_calibration.contracts import seal,read_json
from lightyear_calibration.journey_runtime import JourneySigner


class SnapshotExecution(unittest.TestCase):
    def test_new_denominators_do_not_count_trace_execution_failure_as_judge_kill(self):
        slots=schedule()
        self.assertEqual(len(slots),62)
        self.assertEqual(sum(s['fault']=='none' for s in slots),20)
        self.assertEqual(sum(s['fault']=='duplicate-trace-key' for s in slots),3)
        self.assertEqual(sum(s['fault'] not in ('none','duplicate-trace-key') for s in slots),39)
        self.assertEqual(sum(s['fault']=='candidate-reposts-own-match' and s['scenario']=='procure-to-pay' for s in slots),3)

    def test_signed_controller_failure_replays_exactly_and_tampering_is_judge_error(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);signer=JourneySigner(root);run=root/RUNS/'journey-test';run.mkdir(parents=True)
            plan=seal({'scenario':'operations'});save(run/'plan.json',plan)
            (run/'authority.public.pem').write_bytes(signer.public)
            cleanup=signer.sign({'run_id':run.name,'complete':True});save(run/'cleanup.json',cleanup)
            outcome=signer.sign({'run_id':run.name,'plan_sha256':plan['content_sha256'],
                'cleanup_sha256':cleanup['content_sha256'],'status':'execution-failure',
                'error':{'type':'JourneyAbort','message':'scope-boundary'}})
            save(run/'controller-outcome.json',outcome)
            first=evaluate(run);second=evaluate(run)
            self.assertEqual(first,second);self.assertEqual(first['status'],'execution-failure')
            self.assertEqual(read_json(run/'gate.json'),first)
            outcome['error']['message']='changed';save(run/'controller-outcome.json',outcome)
            self.assertEqual(evaluate(run)['status'],'judge-error')
