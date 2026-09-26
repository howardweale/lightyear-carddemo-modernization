"""Adversarial declaration, known-finding and unconditional-cleanup checks."""
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from lightyear_calibration.contracts import seal, CalibrationError
from lightyear_calibration import journey_order as order, journey_runtime as runtime
from lightyear_execution.journey_network import InternalOnlyNetwork
from lightyear_execution.contracts import ExecutionContractError
from lightyear_workflow.policy import CATALOG, default_policy, parse_policy
from lightyear_workflow.run_store import RunStore
from lightyear_workflow.campaign_journals import check

ROOT=Path(__file__).resolve().parents[1]


class DeclarationTests(unittest.TestCase):
    def setUp(self):self.order=order.load_order(ROOT)

    def test_supplied_harnesses_and_zero_model_projection(self):
        projected=order.factory_order(self.order)
        self.assertEqual(0,projected.max_model_calls)
        self.assertEqual(0,projected.max_model_cost_usd)
        self.assertEqual(2,projected.max_attempts)

    def test_declaration_cannot_change_verifier_expectations(self):
        for mutation in (lambda v:v['expected']['boundary'].update(net_total='0'),
                         lambda v:v['policy'].update(max_model_calls=1),
                         lambda v:v['policy'].update(allow_network=True),
                         lambda v:v['cleanup'].update(containers='keep'),
                         lambda v:v['acceptance']['gates'][0].update(command=['bash','-c','anything'])):
            v=copy.deepcopy(self.order);mutation(v)
            with patch.object(order,'read_json',return_value=v),self.assertRaises((CalibrationError,ValueError)):
                order.load_order(ROOT)

    def test_missing_or_changed_harness_refused(self):
        with patch.object(order,'file_hash',return_value='0'*64),self.assertRaises(CalibrationError):order.load_order(ROOT)

    def test_approval_action_cannot_become_autonomous(self):
        self.assertEqual('approval-required',CATALOG['approve-declaration'].action_class)
        p=default_policy();p['autonomy']['approve-declaration']='auto'
        with self.assertRaises(ValueError):parse_policy(p)

    def test_known_finding_disappearing_is_not_success(self):
        f={'lane':'oracle','check':'fractional-shipment-timestamp-preserved','observed':'2026-09-26T12:34:56',
           'expected':'2026-09-26T12:34:56.123456','passed':False}
        b={'failed_input_preservation_or_business_checks':[f],'passed_check_count':{'oracle':14,'postgresql':15}}
        d={'oracle_exit_code':1,'postgresql_exit_code':0,'exact_oracle_error':True,'postgresql_completed':True}
        self.assertTrue(all(order.known_findings(b,d).values()))
        for field,value in [('failed_input_preservation_or_business_checks',[]),('passed_check_count',{'oracle':15,'postgresql':15})]:
            changed={**b,field:value};self.assertFalse(order.known_findings(changed,d)['timestamp'])
        self.assertFalse(order.known_findings(b,{**d,'oracle_exit_code':0})['locking'])
        self.assertFalse(order.known_findings(b,{**d,'exact_oracle_error':False})['locking'])

    def test_retry_only_environment_errors(self):
        for name in ['container-start','timeout','transient-io']:self.assertTrue(order.classify(name)['retryable'])
        for name in ['entry-state-mismatch','unknown-difference','harness-exception','cancelled','cleanup-failure']:
            self.assertFalse(order.classify(name)['retryable'])

    def test_archived_truncated_primary_diagnostic_is_admitted_but_foreign_secondary_is_not(self):
        import gzip
        import zipfile
        from lightyear_calibration import journey_verify as gates
        with tempfile.TemporaryDirectory() as temp, zipfile.ZipFile(ROOT/order.BOUNDARIES/'evidence.zip') as archive:
            run=Path(temp);folder=run/'case';inputs=order.archived(ROOT)
            manifest=json.loads(archive.read('evidence/diagnostic-first-only/states/after-oracle.json'))
            raw=manifest['tables']['ad_issue']['header']['raw_file']
            issues=[json.loads(line) for line in gzip.decompress(archive.read('evidence/diagnostic-first-only/rows/after/oracle/'+raw)).splitlines()]
            primary=next(row for row in issues if row['loggername']=='org.compiere.model.Query')
            self.assertNotIn('LightyearOperationsTest.creditIncrement',primary['stacktrace'])
            order.save(run/'inputs/diagnostic-issues.json',json.loads(inputs['diagnostic-issues.json']))
            for lane in order.LANES:
                where=folder/'execution'/lane;where.mkdir(parents=True)
                for name in ('execution.json','harness.java','journey.xml'):
                    (where/name).write_bytes(archive.read('evidence/diagnostic-first-only/'+lane+'/'+name))
                (where/'maven.log').write_text('ORA-03049 FOR UPDATE FETCH FIRST 2 ROWS ONLY',encoding='utf-8')
            e=json.loads((folder/'execution/oracle/execution.json').read_bytes())
            order.save(run/'plan.json',seal({'diagnostic_harness_sha256':e['harness_sha256'],'declaration':{'application':{'source_commit':e['application_source_commit']}}}))
            with patch.object(gates,'state',return_value={'tables':{'ad_issue':{}}}), patch.object(gates,'rows',side_effect=lambda path,_:issues if 'after' in path.parts else []):
                result=gates.diagnostic(run,folder)
                self.assertEqual(3,result['oracle_issue_profiles_reproduced'])
                self.assertTrue(result['exact_oracle_error'])
                secondary=next(row for row in issues if row['loggername']!='org.compiere.model.Query')
                secondary['stacktrace']=secondary['stacktrace'].replace('LightyearOperationsTest.creditIncrement','UnrelatedTest.run')
                with self.assertRaises(CalibrationError):gates.diagnostic(run,folder)

    def test_separate_internal_network_requires_ownership_and_no_ports(self):
        policy=InternalOnlyNetwork('journey-'+'a'*32)
        net={'Internal':True,'Name':'private','Labels':{'lightyear.journey':policy.run_id}}
        container={'Config':{'Labels':net['Labels']},'HostConfig':{'NetworkMode':'private','PortBindings':{},'Privileged':False},'NetworkSettings':{'Networks':{'private':{}}}}
        self.assertTrue(policy.verify(net,[container]))
        container['HostConfig']['PortBindings']={'5432/tcp':[{'HostIp':'127.0.0.1','HostPort':''}]}
        container['NetworkSettings']['Ports']={'5432/tcp':[]}
        self.assertTrue(policy.verify(net,[container]))
        container['NetworkSettings']['Ports']={'5432/tcp':[{'HostIp':'127.0.0.1','HostPort':'55555'}]}
        with self.assertRaises(ExecutionContractError):policy.verify(net,[container])
        container['NetworkSettings']['Ports']={}
        for c in [{**net,'Internal':False},{**net,'Labels':{}}]:
            with self.assertRaises(ExecutionContractError):policy.verify(c,[container])
        container['HostConfig']['PortBindings']={'5432/tcp':[{'HostPort':'5432'}]}
        with self.assertRaises(ExecutionContractError):policy.verify(net,[container])

    def test_factory_copy_excludes_native_runtime_but_keeps_declaration(self):
        from lightyear_factory.workspace import IsolatedWorkspace
        with tempfile.TemporaryDirectory() as temp:
            source=Path(temp)/'source';source.mkdir()
            relative=Path('factory/idempiere/ms86-journeys')
            (source/relative/'runs').mkdir(parents=True)
            (source/relative/'runs/lock').write_text('live data')
            (source/relative/'work-order.json').write_text('{}')
            workspace=IsolatedWorkspace(source,Path(temp)/'copy',('factory',));workspace.create()
            self.assertFalse((workspace.root/relative/'runs').exists())
            self.assertTrue((workspace.root/relative/'work-order.json').exists())

    def test_signed_cancel_requires_the_local_authority(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);run=root/order.RUNS/('journey-'+'a'*32);run.mkdir(parents=True)
            signer=runtime.JourneySigner(root)
            order.save(run/'cancel-request.json',{'action':'cancel','run_id':run.name})
            with self.assertRaises(ValueError):runtime.cancelled(run)
            order.save(run/'cancel-request.json',signer.sign({'action':'cancel','run_id':run.name}))
            self.assertTrue(runtime.cancelled(run))

    def test_stale_plan_is_rejected(self):
        expected=seal({'declaration_sha256':'a'*64})
        with patch.object(order,'make_plan',return_value=seal({'declaration_sha256':'b'*64})),self.assertRaises(ValueError):
            order.validate_plan(ROOT,expected,{}, {})

    def test_readonly_process_probe_does_not_terminate_process(self):
        self.assertTrue(runtime.process_alive(os.getpid()))


class LifecycleTests(unittest.TestCase):
    def simulate(self,stop=None,cleanup_failure=False,fault='cancelled'):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        root=Path(temporary.name);run=root/order.RUNS/('journey-'+'b'*32);run.mkdir(parents=True)
        declaration=order.load_order(ROOT)
        plan=seal({'declaration':declaration,'declaration_sha256':'c'*64,'implementation_sha256':{}})
        order.save(run/'plan.json',plan)
        signer=runtime.JourneySigner(root);(run/'authority.public.pem').write_bytes(signer.public)
        auth=signer.sign({'run_id':run.name,'plan':{'plan_sha256':plan['content_sha256']}})
        order.save(run/'authorization.json',auth)
        self.last_root,self.last_run=root,run
        instances=[]
        class FakeRunner:
            def __init__(self,*a):self.live=False;self.cleaned=0;instances.append(self)
            def checkpoint(self,stage):
                if stop==stage:
                    if fault=='unknown':raise ValueError('Unknown difference')
                    raise runtime.JourneyAbort(fault)
            def prepare(self,case,attempt):
                self.live=True;self.checkpoint('prepare');return run
            def execute(self,case,folder):self.checkpoint('execute')
            def gate(self,command):
                self.checkpoint('gate:'+command)
                from lightyear_calibration.journey_verify import verify_gate
                return verify_gate(run,command)
            def cleanup(self,retain=False):
                self.cleaned+=1;self.live=cleanup_failure
                return {'complete':not cleanup_failure,'remaining_containers':['test'] if cleanup_failure else [],
                        'remaining_networks':[],'credentials_destroyed':not cleanup_failure,'retained_data':[],'errors':[]}
        with patch.object(runtime,'validate_plan'),patch.object(runtime,'read_local',return_value={}),patch.object(runtime,'inventory',return_value={}),patch('lightyear_calibration.journey_verify.verify_gate',return_value=seal({'passed':True})),patch.object(runtime,'timestamp_acknowledged',return_value=False):
            result=runtime.execute_run(root,run,FakeRunner)
        return result,instances[0],check(RunStore(run/'journal',read_only=True).events(),auth,signer.public,'journey')

    def test_cancel_prepare_execute_verify_always_cleans(self):
        for stage in ['prepare','execute','verify', *['gate:'+c for c in order.COMMANDS if c!='verify-cleanup']]:
            with self.subTest(stage=stage):
                receipt,runner,events=self.simulate(stage)
                self.assertFalse(runner.live);self.assertGreater(runner.cleaned,0)
                self.assertEqual('failed',receipt['status'])
                self.assertEqual('cancelled',receipt['error']['classification'])

    def test_cleanup_precedes_human_halt_and_does_not_promote_claims(self):
        receipt,runner,events=self.simulate()
        self.assertEqual('halted-for-decision',receipt['status'])
        kinds=[e['type'] for e in events]
        self.assertLess(kinds.index('cleanup'),kinds.index('blocked'))
        self.assertLess(kinds.index('blocked'),kinds.index('halted'))
        self.assertFalse(runner.live)
        for name in order.UNCLAIMED:self.assertFalse(receipt[name])

    def test_injected_timeout_retries_only_to_declared_limit(self):
        receipt,runner,events=self.simulate('execute',fault='timeout')
        self.assertEqual(2,sum(e['type']=='round' for e in events))
        self.assertFalse(runner.live)
        self.assertFalse(receipt['unattended_run'])
        self.assertEqual('timeout',receipt['error']['classification'])

    def test_harness_exception_is_recorded_without_retry(self):
        receipt,runner,events=self.simulate('execute',fault='harness-exception')
        self.assertEqual(1,sum(e['type']=='round' for e in events))
        self.assertFalse(runner.live)
        self.assertFalse(receipt['bounded_operations_equivalence'])

    def test_unknown_difference_requires_human_and_cleans_first(self):
        receipt,runner,events=self.simulate('gate:verify-differences',fault='unknown')
        self.assertEqual('halted-for-decision',receipt['status'])
        blocked=next(e['payload'] for e in events if e['type']=='blocked')
        self.assertEqual('propose-normalization',blocked['request']['action_kind'])
        self.assertFalse(receipt['bounded_operations_equivalence'])
        self.assertFalse(runner.live)

    def test_resume_reruns_only_the_affected_case(self):
        from argparse import Namespace
        receipt,runner,events=self.simulate()
        root,run=self.last_root,self.last_run
        (run/'inputs').mkdir()
        request=next(e['payload']['request'] for e in events if e['type']=='blocked')
        runtime.dispatch_command(root,Namespace(command='decision',run=run,decision_id=request['id'],actor='test-operator',reason='Keep timestamp open for the bounded replay',outcome='retain-open-finding'))
        with patch.object(runtime,'validate_plan'),patch.object(runtime,'read_local',return_value={}),patch.object(runtime,'inventory',return_value={}),patch.object(runtime,'spawn',return_value=123):
            result=runtime.dispatch_command(root,Namespace(command='resume',run=run))
        child=Path(result['run_path']);auth=order.read_json(child/'authorization.json')
        self.assertEqual(['boundary'],auth['cases_to_execute'])
        self.assertEqual({'operations','diagnostic-first-only'},set(auth['case_references']))
        self.assertTrue(all(x['receipt_sha256']==receipt['content_sha256'] for x in auth['case_references'].values()))

    def test_cleanup_failure_never_completes(self):
        receipt,runner,events=self.simulate(cleanup_failure=True)
        self.assertEqual('failed',receipt['status']);self.assertFalse(receipt['unattended_run'])
        self.assertEqual('cleanup-failure',receipt['error']['classification'])


if __name__=='__main__':unittest.main()
