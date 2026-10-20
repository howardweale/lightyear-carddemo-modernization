"""Offline verifier-boundary fixtures; Tower signatures are mocked, never created."""
import copy
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch
from lightyear_factory.contracts import ContractError, canonical_hash
from lightyear_factory.model_admission import FactoryModelAdmission

class FactoryModelAdmissionTests(unittest.TestCase):
    def fixtures(self, root):
        order=SimpleNamespace(content_sha256='a'*64,max_attempts=3,max_elapsed_seconds=60,
                              max_model_calls=6,max_model_tokens=1000,max_model_cost_usd=1)
        provider=SimpleNamespace(provider_id='fixture',model='fixture-2026-10-20',_injected_opener=False)
        caps=dict(max_attempts=3,max_repair_loops=2,max_elapsed_seconds=60,max_model_calls=6,
                  max_model_tokens=1000,cost_cap_microusd=1000000)
        inputs={name:dict(path=name+'.json',sha256='b'*64) for name in ('scope','freeze','workspace','execution_policy')}
        plan=dict(schema='factory-build-plan/1',work_order_sha256=order.content_sha256,executable_commit='c'*40,
                  caps=caps,bound_inputs=inputs,roles={r:dict(provider='fixture',model=provider.model) for r in ('planner','builder','analyst')})
        plan['content_sha256']=canonical_hash(plan)
        contract=dict(kind='engineering-run-approval',sources=list(inputs.values()),details=dict(
            executable_commit='c'*40,request_seal=plan['content_sha256'],caps=caps,
            window=dict(start='2026-10-20T00:00:00+00:00',end='2026-10-21T00:00:00+00:00')))
        proof=dict(decision_sha256='d'*64)
        admission=FactoryModelAdmission(root,'plan.json','proof.json','contract.json',public_key=b'offline-fixture',trusted_head=lambda:'e'*64)
        return admission,order,provider,plan,proof,contract

    def test_existing_tower_verifier_required_and_exact_plan_role_caps_bound(self):
        with tempfile.TemporaryDirectory() as d:
            admission,order,provider,plan,proof,contract=self.fixtures(Path(d))
            now=datetime(2026,10,20,12,tzinfo=timezone.utc)
            with patch.object(admission,'_committed_json',side_effect=[plan,proof,contract]), patch(
                'lightyear_factory.model_admission.subprocess.check_output',side_effect=[b'',b'f'*40,b'',b'proof.json\0']), patch(
                'lightyear_factory.model_admission.FactoryDecisions') as tower:
                result=admission.verify(order,provider,'failure_analyst',now=now)
                self.assertEqual('analyst',result['role'])
                tower.return_value.verify.assert_called_once_with(proof,'engineering-run-approval',contract,{'approve'})
            for mutation in ('seal','cost','provider','injected','code'):
                a,o,p,plan,proof,contract=self.fixtures(Path(d))
                if mutation=='seal':contract['details']['request_seal']='0'*64
                elif mutation=='cost':o.max_model_cost_usd=2
                elif mutation=='provider':p.model='different-2026-10-20'
                elif mutation=='injected':p._injected_opener=True
                diff=b'src/changed.py\0' if mutation=='code' else b''
                with self.subTest(mutation=mutation), patch.object(a,'_committed_json',side_effect=[plan,proof,contract]), patch(
                    'lightyear_factory.model_admission.subprocess.check_output',side_effect=[b'',b'f'*40,b'',diff]), patch(
                    'lightyear_factory.model_admission.FactoryDecisions') as tower, self.assertRaises(ContractError):
                    a.verify(o,p,'builder',now=now)
                tower.return_value.verify.assert_not_called()

    def test_uncommitted_evidence_is_rejected_before_trust_verification(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);a,*_=self.fixtures(root);(root/'plan.json').write_bytes(b'{}')
            with patch('lightyear_factory.model_admission.subprocess.check_output',side_effect=[b'a'*40,b'2',b'[]']):
                with self.assertRaisesRegex(ContractError,'not-committed'):a._committed_json('plan.json')

    def test_metadata_size_and_descriptor_replacement_refused_before_read(self):
        from lightyear_factory.model_admission import _bounded_regular_bytes
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'fixture'; path.write_bytes(b'{}')
            info = path.stat()
            original = Path.stat
            def oversized(candidate, *args, **kwargs):
                value = original(candidate, *args, **kwargs)
                if candidate == path:
                    return SimpleNamespace(st_mode=value.st_mode, st_nlink=1, st_size=65537)
                return value
            with patch.object(Path, 'stat', oversized), patch.object(Path, 'open') as opened:
                with self.assertRaisesRegex(ContractError, '^fixture-bounded-refusal$'):
                    _bounded_regular_bytes(path, 65536, 'fixture-bounded-refusal')
                opened.assert_not_called()
            changed = SimpleNamespace(st_dev=info.st_dev, st_ino=info.st_ino,
                                      st_size=info.st_size+1, st_mtime_ns=info.st_mtime_ns,
                                      st_nlink=info.st_nlink)
            with patch('lightyear_factory.model_admission.os.fstat', return_value=changed):
                with self.assertRaisesRegex(ContractError, '^fixture-bounded-refusal$'):
                    _bounded_regular_bytes(path, 65536, 'fixture-bounded-refusal')
            self.assertEqual(b'{}', _bounded_regular_bytes(path, 65536, 'fixture-bounded-refusal'))

    def test_committed_blob_size_is_checked_before_blob_materialization(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); admission, *_ = self.fixtures(root)
            (root/'plan.json').write_bytes(b'{}')
            for size, error in ((8*1024*1024+1, 'evidence-size'), (3, 'not-committed')):
                with patch('lightyear_factory.model_admission.subprocess.check_output',
                           side_effect=[b'a'*40, str(size).encode()]) as git:
                    with self.assertRaisesRegex(ContractError, error):
                        admission._committed_json('plan.json')
                    self.assertEqual(2, git.call_count)
                    self.assertFalse(any('blob' in call.args[0] for call in git.call_args_list))
            with patch('lightyear_factory.model_admission.subprocess.check_output',
                       side_effect=[b'a'*40, b'2', b'{}']):
                self.assertEqual({}, admission._committed_json('plan.json'))

    def test_dirty_expired_and_advancing_trust_fail_closed(self):
        with tempfile.TemporaryDirectory() as d:
            for failure in ('dirty', 'expired', 'trust-advanced'):
                a,o,p,plan,proof,contract=self.fixtures(Path(d))
                if failure=='trust-advanced':
                    heads=iter(['e'*64,'f'*64]); a.trusted_head=lambda:next(heads)
                now=datetime(2026,10,22 if failure=='expired' else 20,12,tzinfo=timezone.utc)
                git=[b' M changed.py'] if failure=='dirty' else [b'',b'f'*40,b'',b'']
                with self.subTest(failure=failure), patch.object(a,'_committed_json',side_effect=[plan,proof,contract]), patch(
                    'lightyear_factory.model_admission.subprocess.check_output',side_effect=git), patch(
                    'lightyear_factory.model_admission.FactoryDecisions') as tower, self.assertRaises(ContractError):
                    a.verify(o,p,'builder',now=now)
                if failure!='trust-advanced':tower.return_value.verify.assert_not_called()
                else:tower.return_value.verify.assert_called_once()

    def test_each_nonstub_call_checks_current_admission_before_transport(self):
        from lightyear_factory.budgeted_providers import AccountedModelProvider
        from lightyear_factory.providers import BoundedModelProvider
        with tempfile.TemporaryDirectory() as d:
            a,o,p,*_=self.fixtures(Path(d))
            wrapped=AccountedModelProvider(p,o)
            with patch.object(BoundedModelProvider,'complete') as transport:
                with self.assertRaisesRegex(ContractError,'approval-required'):
                    wrapped.complete('builder','private',{}, {})
                transport.assert_not_called()
                wrapped.model_admission=a
                wrapped.runtime_admission=lambda:None
                with patch.object(a,'verify',side_effect=[{'fixture':True},ContractError('expired')]) as admission:
                    wrapped.complete('builder','private',{}, {})
                    with self.assertRaisesRegex(ContractError,'expired'):
                        wrapped.complete('builder','private',{}, {})
                    self.assertEqual(2,admission.call_count)
                    transport.assert_called_once()

    def test_cli_nonlocal_missing_proof_refuses_before_credentials_or_nonce(self):
        from lightyear_factory.cli import main
        for provider in ('openai','configured'):
            with self.subTest(provider=provider), patch('lightyear_factory.cli.verify_work_order') as verify, patch(
                'lightyear_factory.cli.OpenAIAgentSet.from_environment') as credentials, self.assertRaisesRegex(
                ContractError,'factory-model-approval-required'):
                main(['run','--provider',provider])
            verify.assert_not_called();credentials.assert_not_called()

    def test_external_trust_is_separate_and_key_replacement_is_refused(self):
        import json
        with tempfile.TemporaryDirectory() as d:
            outer=Path(d);root=outer/'repo';root.mkdir()
            key=outer/'key.pem';key.write_bytes(b'public-fixture')
            config=outer/'trust.json';record=dict(scope='factory',public_key='key.pem',journal_head_sha256='e'*64)
            config.write_text(json.dumps(record))
            a=FactoryModelAdmission.from_external_trust(root,'plan.json','proof.json','contract.json',config)
            self.assertEqual('e'*64,a.trusted_head())
            record['journal_head_sha256']='f'*64;config.write_text(json.dumps(record))
            self.assertEqual('f'*64,a.trusted_head())
            key.write_bytes(b'replaced-public-fixture')
            with self.assertRaisesRegex(ContractError,'trust-changed'):a.trusted_head()
            (root/'trust.json').write_text(json.dumps(record))
            with self.assertRaisesRegex(ContractError,'external-trust-required'):
                FactoryModelAdmission.from_external_trust(root,'p','a','c',root/'trust.json')

    def test_plan_preflight_verifies_tower_without_claiming_provider_admission(self):
        with tempfile.TemporaryDirectory() as d:
            a,o,p,plan,proof,contract=self.fixtures(Path(d))
            with patch.object(a,'_committed_json',side_effect=[plan,proof,contract]), patch(
                'lightyear_factory.model_admission.subprocess.check_output',side_effect=[b'',b'f'*40,b'',b'']), patch(
                'lightyear_factory.model_admission.FactoryDecisions') as tower:
                result=a.verify_plan(o,now=datetime(2026,10,20,12,tzinfo=timezone.utc))
            tower.return_value.verify.assert_called_once()
            self.assertFalse(result['provider_verified']);self.assertIsNone(result['provider'])
            with self.assertRaisesRegex(ContractError,'provider-required'):a.verify(o,None,'builder')

    def test_cli_valid_envelope_preflights_f2_before_consuming_nonce(self):
        import json
        from lightyear_factory.cli import main
        from unittest.mock import Mock
        with tempfile.TemporaryDirectory() as d:
            envelope=Path(d)/'envelope.json';envelope.write_text(json.dumps({'nonce':'fixture-nonce'}))
            for approved in (False,True):
                events=[];admission=Mock()
                def preflight(order, **kwargs):
                    events.append('f2-proof')
                    if not approved:raise ContractError('fixture-proof-refused')
                    return {'workspace_read_manifest':{'fixture.py':'a'*64}}
                admission.verify_runtime.side_effect=preflight
                admission.private_expected_values.side_effect=lambda *a, **kw: events.append('private-input')
                with self.subTest(approved=approved), patch.object(FactoryModelAdmission,'from_external_trust',return_value=admission), patch(
                    'lightyear_factory.cli.ExecutionPolicy.load'), patch('lightyear_factory.cli.verify_work_order',return_value=(object(),{})) as signed, patch(
                    'lightyear_factory.cli.AdmissionNonceStore') as nonces, patch(
                    'lightyear_factory.cli.OCIContainerBackend'), patch(
                    'lightyear_factory.cli.HardenedExecutionContext',side_effect=ContractError('fixture-stop-after-nonce')), patch(
                    'lightyear_factory.cli.OpenAIAgentSet') as credentials:
                    nonces.return_value.consume.side_effect=lambda nonce:events.append('nonce')
                    with self.assertRaisesRegex(ContractError,'fixture-stop-after-nonce' if approved else 'fixture-proof-refused'):
                        main(['run','--provider','openai','--signed-work-order',str(envelope),
                              '--execution-runtime','docker','--factory-plan','plan.json',
                              '--factory-approval','proof.json','--factory-contract','contract.json',
                              '--factory-trust',str(Path(d)/'trust.json'),'--factory-scope','scope.json',
                              '--factory-freeze','freeze.json','--factory-workspace','workspace.json',
                              '--factory-private-expected-values',str(Path(d)/'private.json')])
                    self.assertIsNone(signed.call_args.args[-1])
                    credentials.assert_not_called()
                    if approved:nonces.return_value.consume.assert_called_once_with('fixture-nonce')
                    else:nonces.assert_not_called()
                self.assertEqual(['f2-proof','private-input','nonce'] if approved else ['f2-proof'],events)

    def test_actual_runtime_manifest_paths_bytes_policy_and_root_are_bound(self):
        import json
        from hashlib import sha256
        from lightyear_execution.contracts import ExecutionPolicy
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);a,o,provider,plan,proof,contract=self.fixtures(root)
            policy=ExecutionPolicy.load(Path(__file__).resolve().parents[1]/'factory/execution/policy.json')
            documents=dict(scope={'fixture':'scope'},freeze={'fixture':'freeze'},
                           workspace={'src/fixture.py':'a'*64},execution_policy=policy.to_dict())
            paths={name:name+'.json' for name in documents}
            for name,value in documents.items():
                raw=json.dumps(value).encode();(root/paths[name]).write_bytes(raw)
                plan['bound_inputs'][name]={'path':paths[name],'sha256':sha256(raw).hexdigest()}
            plan['content_sha256']=canonical_hash(plan,{'content_sha256'})
            def committed(path):
                if path=='plan.json':return plan
                return json.loads((root/path).read_bytes())
            with patch.object(a,'verify_plan',return_value={'plan_sha256':plan['content_sha256']}), patch.object(
                a,'_committed_json',side_effect=committed):
                result=a.verify_runtime(o,source_root=root,input_paths=paths,policy=policy)
                self.assertEqual(documents['workspace'],result['workspace_read_manifest'])
                for failure in ('root','path','manifest','policy','bytes'):
                    supplied=dict(paths);actual_root=root;manifest=documents['workspace'];actual_policy=policy
                    if failure=='root':actual_root=root/'different'
                    if failure=='path':supplied['scope']='different.json'
                    if failure=='manifest':manifest={}
                    if failure=='policy':
                        from dataclasses import replace
                        actual_policy=replace(policy,memory_mb=policy.memory_mb+64)
                    if failure=='bytes':(root/'scope.json').write_text('{"fixture":"changed"}')
                    with self.subTest(failure=failure),self.assertRaises(ContractError):
                        a.verify_runtime(o,source_root=actual_root,input_paths=supplied,
                                         policy=actual_policy,read_manifest=manifest)

    def test_controller_refuses_runtime_manifest_replacement(self):
        from lightyear_factory.orchestrator import FactoryOrchestrator
        from lightyear_factory.agents import LocalAgentSet
        from unittest.mock import Mock
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);a,o,*_=self.fixtures(root)
            controller=FactoryOrchestrator(root,root/'runs',LocalAgentSet(),model_admission=a,
                execution_context=SimpleNamespace(policy=object()),factory_input_paths={'fixture':'path'},
                workspace_read_manifest={'fixture.py':'a'*64})
            with patch.object(a,'verify_runtime',side_effect=ContractError('runtime-workspace')) as verify:
                with self.assertRaisesRegex(ContractError,'runtime-workspace'):controller._verify_runtime_admission(o)
            self.assertEqual(controller.workspace_read_manifest,verify.call_args.kwargs['read_manifest'])
            controller.workspace_read_manifest=None
            with patch.object(a,'verify_runtime') as verify:
                with self.assertRaisesRegex(ContractError,'runtime-workspace'):controller._verify_runtime_admission(o)
            verify.assert_not_called()

    def test_routed_fallback_rechecks_concrete_provider_and_keeps_one_budget(self):
        from lightyear_factory.routing import TaskRouter
        from lightyear_factory.providers import ProviderError, ProviderResult
        from unittest.mock import Mock
        class FixtureProvider:
            provider_id='fixture';manage_failure_budget=True
            model='fixture-2026-10-20';input_usd_per_million=1;output_usd_per_million=1;max_output_tokens=8
            def __init__(self,fail):self.fail=fail;self.invocations=0
            def complete(self,*args):
                self.invocations+=1
                if self.fail:raise ProviderError('builder','fixture-primary-failed')
                return ProviderResult({'ok':True},dict(input_tokens=1,output_tokens=1,
                    estimated_cost_usd=.000002,cost_estimate_available=True))
        with tempfile.TemporaryDirectory() as d:
            a,o,*_=self.fixtures(Path(d));o.metadata={};o.max_model_input_bytes=100000;o.max_model_output_bytes=100000;o.max_model_tokens=100000
            primary,fallback=FixtureProvider(True),FixtureProvider(False)
            router=TaskRouter({'primary':primary,'fallback':fallback},'primary')
            runtime=Mock();budget=router.bind_order(o,model_admission=a,runtime_admission=runtime)
            route=dict(policy={'routes':{'implement':{'primary':'primary','fallback':'fallback'}}},sha256='f'*64)
            with patch('lightyear_factory.routing.admitted_policy',return_value=route),patch.object(a,'verify') as verify:
                result=budget.complete('builder','fixture',{}, {})
                self.assertEqual({'ok':True},result.content)
                self.assertEqual([primary,fallback],[call.args[1] for call in verify.call_args_list])
                self.assertEqual(2,runtime.call_count);self.assertEqual(2,len(budget.calls))
                self.assertEqual('failed',budget.calls[0]['status'])
                self.assertTrue(budget.calls[1]['routing']['fallback'])
                runtime.side_effect=ContractError('runtime-changed')
                with self.assertRaisesRegex(ContractError,'runtime-changed'):
                    budget.complete('builder','fixture',{}, {})
                self.assertEqual(2,verify.call_count)
                self.assertEqual(1,primary.invocations);self.assertEqual(1,fallback.invocations)
                self.assertEqual(2,len(budget.calls))

    def test_agent_entrypoint_refuses_unbound_and_generic_bounded_nonstub(self):
        from lightyear_factory.agents import ModelAgentSet
        from lightyear_factory.providers import BoundedModelProvider
        from lightyear_factory.budgeted_providers import AccountedModelProvider
        from unittest.mock import Mock
        with tempfile.TemporaryDirectory() as d:
            admission,order,provider,*_=self.fixtures(Path(d))
            provider.complete=Mock()
            agent=ModelAgentSet(provider)
            with self.assertRaisesRegex(ContractError,'controller-binding-required'):
                agent._provider_for(order)
            agent.bounded_provider=BoundedModelProvider(provider,order)
            agent.order_sha256=order.content_sha256
            with self.assertRaisesRegex(ContractError,'controller-binding-required'):
                agent._provider_for(order)
            bound=AccountedModelProvider(provider,order,model_admission=admission,runtime_admission=Mock())
            agent.bounded_provider=bound
            self.assertIs(bound,agent._provider_for(order))
            with self.assertRaisesRegex(ContractError,'controller-binding-required'):
                agent._provider_for(copy.copy(order))
            provider.complete.assert_not_called()

    def test_private_expected_values_bind_approved_bytes_and_refuse_replacement(self):
        import json
        from hashlib import sha256
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)/'source'; root.mkdir()
            private = Path(d)/'expected.json'
            value = 'private expected answer ' * 4
            raw = json.dumps({'schema':'factory-private-expected-values/1','values':[value]}).encode()
            private.write_bytes(raw)
            admission, order, _, plan, _, _ = self.fixtures(root)
            plan['private_expected_values'] = dict(sha256=sha256(raw).hexdigest(),size_bytes=len(raw),count=1)
            plan['content_sha256'] = canonical_hash(plan, {'content_sha256'})
            with patch.object(admission,'verify_plan',return_value={'plan_sha256':plan['content_sha256']}), patch.object(
                    admission,'_committed_json',return_value=plan):
                self.assertEqual((value,), admission.private_expected_values(order,private))
                for location in (root/'copied.json', Path(d)/'runs'/'copied.json'):
                    location.parent.mkdir(exist_ok=True); location.write_bytes(raw)
                    with self.assertRaisesRegex(ContractError,'private-expected-values-refused'):
                        admission.private_expected_values(order,location,excluded_roots=(Path(d)/'runs',))
                private.write_bytes(raw.replace(b'private',b'changed'))
                with self.assertRaisesRegex(ContractError,'private-expected-values-refused') as caught:
                    admission.private_expected_values(order,private)
                self.assertNotIn(value,str(caught.exception))
                self.assertNotIn(str(private),str(caught.exception))
                private.write_bytes(raw)
                with patch.object(Path,'is_symlink',return_value=True), self.assertRaises(ContractError):
                    admission.private_expected_values(order,private)

    def test_private_expected_values_missing_or_oversized_binding_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            admission, order, _, plan, _, _ = self.fixtures(Path(d))
            for binding in ({}, {'sha256':'a'*64,'size_bytes':262145,'count':1},
                            {'sha256':'a'*64,'size_bytes':10,'count':0}):
                plan['private_expected_values']=binding
                plan['content_sha256']=canonical_hash(plan,{'content_sha256'})
                with patch.object(admission,'verify_plan',return_value={'plan_sha256':plan['content_sha256']}), patch.object(
                        admission,'_committed_json',return_value=plan), patch.object(Path,'open') as read:
                    with self.assertRaisesRegex(ContractError,'private-expected-values-refused'):
                        admission.private_expected_values(order,Path(d)/'unused')
                    read.assert_not_called()
