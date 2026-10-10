import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock

from lightyear_calibration.contracts import seal
from tools import ms94_b06_engineering as e
from tools.ms94_b06_engineering_boundary import refuse_engineering


def reseal(value, **changes):
    return seal({**{k:v for k,v in value.items() if k!='content_sha256'}, **changes})


class EngineeringTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name); self.evidence=self.root/'evidence'; self.evidence.mkdir()
        self.a=e.proposal('2026-10-10T23:00:00Z','2026-10-11T23:00:00Z',
            [dict(start='2026-10-10T19:30:00Z',end='2026-10-10T22:30:00Z')], [str(self.evidence)], self.root/'b06-engineering')
        self.clock=patch.object(e,'now',return_value=datetime(2026,10,11,1,tzinfo=timezone.utc)); self.clock.start(); self.addCleanup(self.clock.stop)

    def test_proposal_cannot_authorize(self):
        path=self.root/'approval.json'; e.write_new(path,self.a)
        with self.assertRaisesRegex(ValueError,'approval-required'): e.approve_check(self.a,e.sha(path),path)

    def test_exact_approval_digest_required(self):
        a=reseal(self.a,artifact_type='b06-engineering-standing-approval/1',approved=True,
            approved_by='Howard',approval_reference='chat-123',approved_at_utc='2026-10-10T23:00:00Z')
        path=self.root/'approval.json'; e.write_new(path,a); e.approve_check(a,e.sha(path),path)
        with self.assertRaisesRegex(ValueError,'approval-file-changed'): e.approve_check(a,'0'*64,path)

    def test_image_policy_cap_scope_and_limits_not_widened(self):
        for change in (dict(image='sha256:'+'0'*64),dict(run_cap=11),dict(run_cap=True),
                       dict(scope='pair'),dict(limits={**e.LIMITS,'candidate_seconds':9999}),
                       dict(no_degradation=False),dict(model_calls=1),dict(qualification_credit=True)):
            with self.subTest(change=change),self.assertRaises(ValueError):e.validate(reseal(self.a,**change))

    def test_window_overlap_refused(self):
        with self.assertRaisesRegex(ValueError,'overlap'):
            e.validate(reseal(self.a,not_before_utc='2026-10-10T22:00:00Z',deadline_utc='2026-10-11T22:00:00Z'))

    def test_full_budget_and_expired_window(self):
        with self.assertRaisesRegex(ValueError,'full-run-budget'):
            e.guard(self.a,datetime(2026,10,11,22,tzinfo=timezone.utc),starting=True)
        with self.assertRaisesRegex(ValueError,'outside-window'):
            e.guard(self.a,datetime(2026,10,11,23,tzinfo=timezone.utc))

    def test_armed_evidence_blocks_even_before_started(self):
        e.write_new(self.evidence/'armed.json',{})
        with self.assertRaisesRegex(ValueError,'evidence-launcher-active'): e.guard(self.a)

    def test_missing_registry_fails_closed(self):
        self.evidence.rmdir()
        with self.assertRaisesRegex(ValueError,'registry-unavailable'): e.guard(self.a)

    def test_consumed_failed_attempt_and_no_retry(self):
        ledger=e.Ledger(self.root/'b06-engineering',self.a)
        with ledger.lock():
            first=ledger.reserve('a'*40)
            with self.assertRaisesRegex(ValueError,'prior-run-unsealed'): ledger.reserve('b'*40)
        self.assertTrue((ledger.root/'active.lock').exists())
        with self.assertRaises(FileExistsError):
            with ledger.lock(): self.fail('must not enter')

    def test_ten_consumed_attempts_stop(self):
        ledger=e.Ledger(self.root/'b06-engineering',self.a)
        with ledger.lock():
            for i in range(10):
                run=ledger.reserve('a'*40)
                self.assertEqual(json.loads((run/'engineering.json').read_text())['run_number'],i+1)
                e.write_new(run/'terminal.json',dict(**e.LABEL,cleanup_verified=True,outcome='refused'))
                e.write_new(run/'artifacts.json',dict(**e.LABEL))
            with self.assertRaisesRegex(ValueError,'run-cap-exhausted'): ledger.reserve('b'*40)
        self.assertFalse((ledger.root/'active.lock').exists())

    def test_output_link_and_wrong_root_refused(self):
        with self.assertRaisesRegex(ValueError,'output-root'):e.Ledger(self.root/'factory',self.a)

    def test_signed_bodies_and_binary_descriptors_labelled(self):
        signer=Mock(public=b'fixture',sign=lambda body:seal(body)); wrapped=e.EngineeringSigner(signer)
        value=wrapped.sign(dict(qualification_credit=True)); self.assertEqual(value['run_class'],'engineering')
        self.assertFalse(value['qualification_credit'])
        run=self.root/'run';run.mkdir();(run/'raw.bin').write_bytes(b'original bytes')
        result=e.seal_artifacts(run,wrapped)
        self.assertEqual(result['artifacts'][0]['sha256'],e.sha(run/'raw.bin'))
        self.assertEqual(result['artifacts'][0]['run_class'],'engineering')
        self.assertEqual((run/'raw.bin').read_bytes(),b'original bytes')

    def test_recursive_and_renamed_artifact_refusal(self):
        with self.assertRaisesRegex(ValueError,'not-admissible'):refuse_engineering(dict(rows=[dict(**e.LABEL)]))
        folder=self.root/'renamed';folder.mkdir();e.write_new(folder/'engineering.json',{})
        with self.assertRaisesRegex(ValueError,'not-admissible'):refuse_engineering({},folder/'raw.bin')

    def test_actual_qualification_census_measurement_entrypoints_refuse(self):
        from tools.ms94_b06_admission import verify_inputs
        from tools.ms94_b06_qualification_driver import execute_group
        from tools.ms94_b06_measurement_admission import builder_gate
        from tools.ms94_b06_group_decision import request
        from tools.ms94_b06_controller import Controller
        value=seal(dict(**e.LABEL))
        calls=(lambda:verify_inputs(self.root,value),lambda:execute_group(self.root,value,self.root,None,authority_root=self.root),
               lambda:builder_gate(value,None),lambda:request(value,'a'*40),
               lambda:Controller(self.root,None,value,None,monotonic=lambda:0))
        for call in calls:
            with self.assertRaisesRegex(ValueError,'not-admissible'):call()

    def test_replay_cannot_promote_even_with_resealed_plan(self):
        from tools.ms94_b06_qualification_replay import replay_pair
        run=self.root/'run';run.mkdir();e.write_new(run/'plan.json',seal(dict(**e.LABEL)))
        with self.assertRaisesRegex(ValueError,'not-admissible'):replay_pair(self.root,run,b'fixture')

    def test_oracle_setup_never_creates_postgres_or_volume(self):
        from tools import ms94_b06_engineering_native as n
        owner='journey-'+'a'*32;run=self.root/owner;run.mkdir()
        plan=dict(declaration=dict(policy=dict(max_elapsed_seconds=3600),environment=dict(engines=dict(
            oracle=dict(image_digest='oracle-image',expected_version='version')))),local=dict(runner_image='carrier'))
        runner=n.OracleEngineeringRunner(self.root,run,plan,lambda *_:None,self.a)
        runner.checkpoint=Mock();runner.assert_real_runtime=Mock();runner.rotate_passwords=Mock();runner.worker=Mock()
        calls=[]
        with patch.object(n,'docker',side_effect=lambda *args,**kw:calls.append(args)),patch.object(n,'inspect',return_value={}),             patch.object(n.InternalOnlyNetwork,'verify',return_value=True),patch.object(n,'oracle_baseline'):runner.prepare()
        self.assertEqual(set(runner.names),{'oracle'})
        self.assertFalse(any('postgresql' in str(c) or c[:2]==('volume','create') for c in calls))
        creates=[c for c in calls if c[0]=='create'];self.assertEqual(len(creates),2)
        self.assertTrue(all('--memory' in c and '--cpus' in c for c in creates))
        self.assertEqual(runner.worker.call_args.args[1]['lane'],'oracle')
        with self.assertRaisesRegex(ValueError,'oracle-only'):
            n.OracleEngineeringRunner.worker(runner,'execute',dict(lane='postgresql'),10)

    def test_prepare_failure_always_cleans_owned_resources(self):
        from tools import ms94_b06_engineering_native as n
        run=self.root/'run';run.mkdir();e.write_new(run/'plan.json',dict(declaration=dict(policy=dict(max_elapsed_seconds=3600))))
        signer=Mock(sign=lambda value:seal(value))
        with patch.object(n.OracleEngineeringRunner,'prepare',side_effect=ValueError('failure')),             patch.object(n,'cleanup_owned',return_value=dict(complete=True)) as clean,patch.object(n,'absence',return_value=True):
            result=n.execute(self.root,run,self.a,signer)
        clean.assert_called_once();self.assertEqual(result['outcome'],'refused');self.assertTrue(result['cleanup_verified'])

    def test_output_root_cannot_reset_approved_run_cap(self):
        other=self.root/'other'/'b06-engineering'
        with self.assertRaisesRegex(ValueError,'approval-output-root'):e.Ledger(other,self.a)

    def test_worker_cannot_resign_an_existing_envelope(self):
        signer=e.EngineeringSigner(Mock(public=b'fixture'))
        with self.assertRaisesRegex(ValueError,'already-signed-body'):
            signer.sign(dict(signature={},content_sha256='a'*64))

    def test_sealing_failure_retains_lease_even_with_terminal(self):
        ledger=e.Ledger(self.root/'b06-engineering',self.a)
        with self.assertRaisesRegex(RuntimeError,'publication'):
            with ledger.lock():
                run=ledger.reserve('a'*40)
                e.write_new(run/'terminal.json',dict(cleanup_verified=True))
                e.write_new(run/'artifacts.json',{})
                raise RuntimeError('publication')
        self.assertTrue((ledger.root/'active.lock').exists())

    def test_oracle_baseline_rejects_changed_seed_and_failed_probe(self):
        from tools.ms94_b06_engineering_native import oracle_baseline
        from lightyear_calibration.contracts import seal
        run=self.root/'run';(run/'inputs').mkdir(parents=True)
        e.write_new(run/'inputs/oracle-entry-multisets.json',{'T':'expected'})
        e.write_new(run/'inputs/checkpoint.json',dict(content_sha256='checkpoint'))
        base=run/'base';base.mkdir()
        probes=seal(dict(catalog_sha256='catalog',expected_cases=30,expectations_met=30,
            cases=[dict(expectation_met=True)]*30,transaction_rolled_back=True))
        e.write_new(base/'probes.json',probes)
        state=dict(tables={'T':dict(row_multiset='expected')},content_sha256='state')
        catalog=dict(content_sha256='catalog',import_binding=dict(ms84_checkpoint_sha256='checkpoint',state_sha256='state'))
        with patch('lightyear_calibration.native_reconciliation.state',return_value=state),patch('lightyear_calibration.native_catalog.read_capture',return_value=catalog):
            oracle_baseline(run,base)
            state['tables']['T']['row_multiset']='changed'
            with self.assertRaisesRegex(ValueError,'multisets'):oracle_baseline(run,base)

    def test_context_and_log_preserve_identifiers_not_invent_outcomes(self):
        run=self.root/'run';p=run/'posting-observer/oracle/events.jsonl';p.parent.mkdir(parents=True)
        events=[dict(event=dict(kind='observer-audit',action='jdi-event',detail=dict(thread_id=7,depth=101,method='spinInnerClass'))),
                dict(event=dict(kind='observer-audit',action='dispatch-refused',sequence=3,detail={}))]
        p.write_text(''.join(json.dumps(x)+'\n' for x in events))
        context=e.refusal_context(run);self.assertEqual(context['preceding_event']['detail']['depth'],101)
        log=self.root/'log.md';e.append_log(log,dict(run_number=1,source_commit='a'*40),dict(outcome='refused'),context)
        self.assertIn('| 3 | 7 | spinInnerClass | 101 | engineering | false | false |',log.read_text())


if __name__=='__main__':unittest.main()
