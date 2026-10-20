from hashlib import sha256
import base64
from unittest.mock import patch
import json
import os
from pathlib import Path
import tempfile
import unittest
from lightyear_factory.contracts import ContractError
from lightyear_factory.workspace import IsolatedWorkspace
from lightyear_factory.gates import builder_failure_view, GateRunner, CandidateBuildBackend
from lightyear_execution.backend import OCIContainerBackend, LocalProcessBackend
from lightyear_execution.contracts import ExecutionPolicy, ExecutionContractError
from lightyear_factory.orchestrator import FactoryOrchestrator
from lightyear_factory.isolation_scan import scan

class FactoryAllowlistFeedbackTests(unittest.TestCase):
    def test_copy_only_exact_files_without_history_or_private_judge(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source=root/'source';source.mkdir()
            for p,text in {'public/input.txt':'public fixture','.git/config':'history',
                           'private/reference.txt':'secret expected output'}.items():
                target=source/p;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(text)
            manifest={'public/input.txt':sha256(b'public fixture').hexdigest()}
            workspace=IsolatedWorkspace(source,root/'workspace',('candidate',),manifest)
            workspace.create();self.assertEqual(manifest,workspace.full_manifest())
            self.assertFalse((workspace.root/'.git').exists());self.assertFalse((workspace.root/'private').exists())
            (workspace.root/'candidate').mkdir();(workspace.root/'candidate/toy.txt').write_text('fixture output')
            self.assertIn('candidate/toy.txt',workspace.verify_read_boundary())
            (workspace.root/'public/input.txt').write_text('changed')
            with self.assertRaisesRegex(ContractError,'readonly-changed'):workspace.verify_read_boundary()

    def test_hash_path_and_link_refusals_precede_copy(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source=root/'source';source.mkdir();(source/'input').write_text('input')
            for path in ('../escape','.git/config','.GIT/config','/absolute','C:/escape',r'a\b','a//b'):
                with self.assertRaises(ContractError):IsolatedWorkspace(source,root/'dest',('candidate',),{path:'a'*64})
            workspace=IsolatedWorkspace(source,root/'dest',('candidate',),{'input':'0'*64})
            with self.assertRaisesRegex(ContractError,'hash-mismatch'):workspace.create()
            self.assertFalse(workspace.root.exists())
            if os.name!='nt':
                (source/'link').symlink_to(source/'input')
                linked=IsolatedWorkspace(source,root/'linked',('candidate',),{'link':sha256(b'input').hexdigest()})
                with self.assertRaisesRegex(ContractError,'symlink'):linked.create()
            workspace=IsolatedWorkspace(source,root/'dest',('candidate',),{'input':sha256(b'input').hexdigest()});workspace.create()
            (workspace.root/'unlisted').write_text('unexpected')
            with self.assertRaisesRegex(ContractError,'unlisted-file'):workspace.verify_read_boundary()
            (workspace.root/'unlisted').unlink();(workspace.root/'.git').mkdir()
            with self.assertRaisesRegex(ContractError,'history'):workspace.verify_read_boundary()

    def test_gateway_never_forwards_values_trace_output_or_analyst_prose(self):
        vocabulary=dict(screens=['FIXTURE'],fields=['FIELD'],tables=['TABLE'])
        private='expected-private-value-012345678901234567890123456789'
        report=dict(status='failed',expected=private,trace=private,gates=[dict(expose_output_to_builder=True,stdout=private)],
                    differences=[dict(interaction=7,screen='FIXTURE',field='FIELD',category='value',expected=private,actual=private)])
        public=builder_failure_view(report,vocabulary)
        self.assertEqual(dict(status='failed',differences=[dict(interaction=7,screen='FIXTURE',field='FIELD',category='value')]),public)
        envelope=FactoryOrchestrator._failure_envelope(public,dict(summary=private,builder_guidance=private),include_diagnosis=False)
        self.assertNotIn(private,json.dumps(envelope));self.assertEqual(public,envelope)
        for key,value in [('screen',private),('field',private),('category',private),('interaction',True)]:
            bad=json.loads(json.dumps(report));bad['differences'][0][key]=value
            with self.assertRaises(ContractError):builder_failure_view(bad,vocabulary)

    def test_three_canary_classes_and_any_expected_forty_character_run_fail(self):
        canaries={k:k+'-UNIQUE-'+'x'*40 for k in ('expected-state','reference-output','session-answer')}
        expected='0123456789'*6
        clean=scan([('fixture prompt','public inputs only')],canaries,[expected]);self.assertEqual('passed',clean['status'])
        for text in [*canaries.values(),expected[9:49]]:
            for artifact in ('prompt','response','tool-call','workspace-file'):
                with self.assertRaisesRegex(ContractError,'^isolation-breach$'):scan([(artifact,text)],canaries,[expected])
        escaped='line\n'*12
        with self.assertRaisesRegex(ContractError,'isolation-breach'):
            scan([('response',json.dumps({'content':escaped}))],canaries,[escaped])
        with self.assertRaisesRegex(ContractError,'canary-classes'):scan([],{},[])

    def test_normalized_and_encoded_leaks_fail_without_private_error_text(self):
        canaries = {k: k + '-PRIVATE-abcdefgh0123456789ABCDEFGHIJ9876543210' for k in
                    ('expected-state', 'reference-output', 'session-answer')}
        expected = 'PrivateReferenceResult-AbCdEf0123456789-ReceiptValue-9876543210'
        encoders = [lambda s: s.swapcase(), lambda s: ' \n'.join(s),
                    lambda s: base64.b64encode(s.encode()).decode(), lambda s: s.encode().hex(),
                    lambda s: ''.join('%%%02X' % b for b in s.encode()),
                    lambda s: base64.b64encode(s.encode().hex().encode()).decode(),
                    lambda s: ' '.join(base64.b64encode(s.encode()).decode()[i:i+4]
                                      for i in range(0, len(base64.b64encode(s.encode())), 4))]
        for secret in [*canaries.values(), expected[3:43]]:
            for encode in encoders:
                for artifact in ('prompt', 'response', 'tool-call', 'workspace-file'):
                    with self.subTest(artifact=artifact, encoded=encode.__name__):
                        with self.assertRaises(ContractError) as caught:
                            scan([(artifact, encode(secret))], canaries, [expected])
                        self.assertEqual('isolation-breach', str(caught.exception))
        for encode in encoders[2:6]:
            with self.assertRaisesRegex(ContractError, '^isolation-breach$'):
                scan([('response', json.dumps({'answer': 'prefix ' + encode(expected) + ' suffix'}))], canaries, [expected])
        raw = b'public fixture response'
        result = scan([('response', raw)], canaries, [expected])
        self.assertEqual(sha256(raw).hexdigest(), result['scanned'][0]['sha256'])
        with patch('lightyear_factory.isolation_scan.MAX_BYTES', 16):
            with self.assertRaisesRegex(ContractError, '^isolation-scan-limit$'):
                scan([('response', b'x'*17)], canaries, [])
        with patch('lightyear_factory.isolation_scan.MAX_DEPTH', 0):
            with self.assertRaisesRegex(ContractError, '^isolation-scan-limit$'):
                scan([('response', base64.b64encode(b'benign fixture data'))], canaries, [])

    def test_structured_prompt_counts_nodes_separately_from_unique_decoded_views(self):
        from lightyear_factory.agents import PLANNER_SCHEMA
        from lightyear_factory.isolation_scan import MAX_JSON_NODES
        canaries = {k: k + '-PRIVATE-abcdefgh0123456789ABCDEFGHIJ9876543210' for k in
                    ('expected-state', 'reference-output', 'session-answer')}
        expected = 'PrivateReferenceResult-AbCdEf0123456789-ReceiptValue-9876543210'
        payload = {'schema': PLANNER_SCHEMA,
                   'catalog': [{'id': 'public', 'paths': ['candidate'], 'kind': 'fixture'} for _ in range(200)]}
        raw = json.dumps(payload).encode()
        result = scan([('planner-prompt', raw)], canaries, [expected])
        self.assertEqual('passed', result['status'])
        self.assertEqual(sha256(raw).hexdigest(), result['scanned'][0]['sha256'])
        payload['catalog'][-1]['id'] = base64.b64encode(expected.encode()).decode()
        with self.assertRaisesRegex(ContractError, '^isolation-breach$'):
            scan([('planner-prompt', json.dumps(payload))], canaries, [expected])
        with self.assertRaisesRegex(ContractError, '^isolation-scan-limit$'):
            scan([('oversized-structure', json.dumps([0] * MAX_JSON_NODES))], canaries, [])
        with patch('lightyear_factory.isolation_scan.MAX_VIEWS', 4):
            with self.assertRaisesRegex(ContractError, '^isolation-scan-limit$'):
                scan([('distinct-views', json.dumps(['one', 'two', 'three', 'four']))], canaries, [])

    def test_receipt_sized_unique_views_still_scan_encoded_leaks_and_refuse_overflow(self):
        from lightyear_factory.isolation_scan import MAX_VIEWS
        canaries = {k: k + '-PRIVATE-abcdefgh0123456789ABCDEFGHIJ9876543210' for k in
                    ('expected-state', 'reference-output', 'session-answer')}
        expected = 'PrivateReferenceResult-AbCdEf0123456789-ReceiptValue-9876543210'
        receipt = {'schema_version': 'fixture-receipt/1', 'evidence': [
            {'artifact': 'event-' + str(i), 'sha256': sha256(str(i).encode()).hexdigest()}
            for i in range(256)]}
        raw = json.dumps(receipt).encode()
        result = scan([('run-receipt-before-memory', raw)], canaries, [expected])
        self.assertEqual('passed', result['status'])
        self.assertEqual(sha256(raw).hexdigest(), result['scanned'][0]['sha256'])
        receipt['evidence'][-1]['artifact'] = base64.b64encode(expected.encode().hex().encode()).decode()
        with self.assertRaisesRegex(ContractError, '^isolation-breach$'):
            scan([('run-receipt-before-memory', json.dumps(receipt))], canaries, [expected])
        # Root view plus MAX_VIEWS distinct, short JSON strings exceeds the cap.
        with self.assertRaisesRegex(ContractError, '^isolation-scan-limit$'):
            scan([('too-many-views', json.dumps(['v%05d' % i for i in range(MAX_VIEWS)]))], canaries, [])

    def test_allowlist_creation_plants_private_canaries_without_source_changes(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); source = root/'source'; source.mkdir()
            (source/'input.txt').write_bytes(b'public input')
            manifest = {'input.txt': sha256(b'public input').hexdigest()}
            workspace = IsolatedWorkspace(source, root/'worker', ('candidate',), manifest)
            workspace.create()
            self.assertEqual({'expected-state', 'reference-output', 'session-answer'}, set(workspace.canaries))
            self.assertEqual(3, len(set(workspace.canaries.values())))
            self.assertEqual(manifest, workspace.full_manifest())
            self.assertNotIn(workspace.root, workspace.canary_root.parents)
            self.assertEqual(['input.txt'], sorted(p.name for p in source.iterdir()))
            self.assertEqual(b'public input', (source/'input.txt').read_bytes())
            for kind, token in workspace.canaries.items():
                self.assertEqual(token, (workspace.canary_root/(kind+'.txt')).read_text())
                self.assertNotIn(token.encode(), (workspace.root/'input.txt').read_bytes())
                with self.assertRaisesRegex(ContractError, '^isolation-breach$'):
                    scan([('tool-call', base64.b64encode(token.encode()))], workspace.canaries, [])
            other = IsolatedWorkspace(source, root/'other', ('candidate',), manifest)
            other.create()
            self.assertTrue(set(workspace.canaries.values()).isdisjoint(other.canaries.values()))
            refused = IsolatedWorkspace(source, root/'refused', ('candidate',), manifest)
            refused.canary_root.mkdir()
            (refused.canary_root/'human.txt').write_text('preserve')
            with self.assertRaisesRegex(ContractError, '^workspace-canary-store-exists$'):
                refused.create()
            self.assertFalse(refused.root.exists())
            self.assertEqual('preserve', (refused.canary_root/'human.txt').read_text())

    def test_candidate_gates_refuse_host_fake_simulated_or_networked_backends(self):
        policy = ExecutionPolicy.load(Path(__file__).resolve().parents[1]/'factory/execution/policy.json')
        with tempfile.TemporaryDirectory() as d, patch.object(LocalProcessBackend, 'execute') as host:
            root = Path(d)
            class Fake:
                assurance = 'enforced'
                execute_enabled = True
            for backend in (None, LocalProcessBackend(), Fake(), OCIContainerBackend(policy, 'docker', execute=False)):
                with self.assertRaisesRegex(ContractError, '^isolation-breach: candidate-container-required$'):
                    GateRunner(root, backend=backend, require_container=True)
            real = OCIContainerBackend(policy, 'docker', execute=True)
            with self.assertRaisesRegex(ContractError, '^isolation-breach'):
                GateRunner(root, allow_network=True, backend=real, require_container=True)
            host.assert_not_called()

    def test_candidate_build_invocation_has_only_readonly_workspace_and_private_tmp_build(self):
        policy = ExecutionPolicy.load(Path(__file__).resolve().parents[1]/'factory/execution/policy.json')
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            runner = GateRunner(root, backend=OCIContainerBackend(policy, 'docker', execute=True), require_container=True)
            self.assertIs(type(runner.backend), CandidateBuildBackend)
            invocation, evidence = runner.backend.build_invocation(
                ('python3', 'candidate-test.py', '; touch /host-marker'), root,
                {'OPENAI_API_KEY': 'fixture-secret', 'PYTHONPATH': '/host/private',
                 'LIGHTYEAR_FACTORY_WORKSPACE': '/host/private'})
            self.assertEqual(1, invocation.count('--mount'))
            self.assertEqual('type=bind,src='+str(root.resolve())+',dst=/workspace,readonly', invocation[invocation.index('--mount')+1])
            self.assertEqual('none', invocation[invocation.index('--network')+1])
            self.assertIn('--read-only', invocation)
            self.assertNotIn('fixture-secret', ' '.join(invocation))
            self.assertNotIn('/host/private', ' '.join(invocation))
            image = invocation.index(policy.image_reference)
            self.assertEqual(['/bin/sh', '-ec', CandidateBuildBackend.LAUNCHER, 'factory-build',
                              'python3', 'candidate-test.py', '; touch /host-marker'], invocation[image+1:])
            self.assertEqual('/tmp/factory-build', evidence['candidate_build_root'])
            self.assertTrue(evidence['workspace_read_only'])
            with self.assertRaises(ExecutionContractError):
                runner.backend.build_invocation(('unapproved-tool',), root, {})

    def test_agent_scans_prompt_before_call_and_response_before_return(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        from lightyear_factory.agents import ModelAgentSet
        from lightyear_factory.providers import ScriptedModelProvider, ProviderResult
        token='CANARY-'+'X'*50
        canaries={'expected-state':token,'reference-output':'R'*60,'session-answer':'S'*60}
        agent=ModelAgentSet(ScriptedModelProvider([]))
        order=SimpleNamespace(content_sha256='a'*64)
        bounded=Mock();bounded.calls=[]
        agent.isolation_scan=lambda name,raw:scan([(name,raw)],canaries,())
        with patch.object(agent,'_provider_for',return_value=bounded):
            with self.assertRaisesRegex(ContractError,'isolation-breach'):
                agent._call(order,'planner','fixture',{'leak':token},{})
            bounded.complete.assert_not_called()
            bounded.complete.return_value=ProviderResult({'leak':token},{})
            with self.assertRaisesRegex(ContractError,'isolation-breach'):
                agent._call(order,'builder','fixture',{}, {})
            self.assertEqual(1,bounded.complete.call_count)
            bounded.complete.return_value=ProviderResult({'safe':'fixture'},{})
            self.assertEqual({'safe':'fixture'},agent._call(order,'failure_analyst','fixture',{},{}))

    def test_controller_binds_canary_scan_without_public_values_or_reuse(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        from lightyear_factory.agents import ModelAgentSet
        from lightyear_factory.providers import ScriptedModelProvider
        canaries={'expected-state':'A'*60,'reference-output':'B'*60,'session-answer':'C'*60}
        controller=FactoryOrchestrator(Path('.'),Path('unused'),ModelAgentSet(ScriptedModelProvider([])))
        ledger=Mock();controller._bind_isolation_scan(SimpleNamespace(canaries=canaries),ledger)
        controller.agents.isolation_scan('planner-prompt',b'public fixture')
        public=json.dumps(ledger.append.call_args.args)
        self.assertFalse(any(value in public for value in canaries.values()))
        self.assertIn(sha256(b'public fixture').hexdigest(),public)
        with self.assertRaisesRegex(ContractError,'agent-reuse'):
            controller._bind_isolation_scan(SimpleNamespace(canaries=canaries),ledger)

    def test_gate_scans_full_output_before_truncation_and_refuses_command_before_execute(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        canaries={'expected-state':'A'*60,'reference-output':'B'*60,'session-answer':'C'*60}
        scanner=lambda name,raw:scan([(name,raw)],canaries,())
        gate=SimpleNamespace(command=('python3','fixture.py'),timeout_seconds=1,
                             gate_id='fixture',expose_output_to_builder=True)
        with tempfile.TemporaryDirectory() as d:
            backend=Mock()
            runner=GateRunner(Path(d),backend=backend,isolation_scan=scanner)
            for stdout,stderr,timed_out in ((b'A'*60+b'z'*70000,b'',False),
                                           (b'',b'B'*60+b'z'*70000,True)):
                backend.execute.return_value=SimpleNamespace(stdout=stdout,stderr=stderr,
                    evidence={},exit_code=1,timed_out=timed_out,duration_ms=1)
                with self.assertRaisesRegex(ContractError,'^gate-isolation-refused$'):
                    runner.run((gate,))
            backend.reset_mock()
            gate.command=('python3','C'*60)
            with self.assertRaisesRegex(ContractError,'^gate-isolation-refused$'):
                runner.run((gate,))
            backend.execute.assert_not_called()

    def test_gate_scan_safe_output_and_private_backend_error_redaction(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        canaries={'expected-state':'A'*60,'reference-output':'B'*60,'session-answer':'C'*60}
        seen=[]
        def scanner(name,raw):
            seen.append(name)
            return scan([(name,raw)],canaries,())
        gate=SimpleNamespace(command=('python3','fixture.py'),timeout_seconds=1,
                             gate_id='fixture',expose_output_to_builder=True)
        with tempfile.TemporaryDirectory() as d:
            backend=Mock();runner=GateRunner(Path(d),backend=backend,isolation_scan=scanner)
            backend.execute.return_value=SimpleNamespace(stdout=b'ok',stderr=b'',evidence={},
                exit_code=0,timed_out=False,duration_ms=1)
            self.assertEqual('passed',runner.run((gate,))['status'])
            self.assertEqual(['gate-command','gate-stdout','gate-stderr','gate-execution-evidence'],seen)
            backend.execute.side_effect=RuntimeError('A'*60)
            with self.assertRaisesRegex(ContractError,'^gate-isolation-refused$'):
                runner.run((gate,))
            backend.execute.side_effect=RuntimeError('private path should not be public')
            with self.assertRaisesRegex(ContractError,'^gate-execution-refused$'):
                runner.run((gate,))

    def test_controller_context_scan_precedes_return_and_gate_reuses_same_scanner(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        from lightyear_factory.agents import ModelAgentSet
        from lightyear_factory.providers import ScriptedModelProvider
        canaries={'expected-state':'A'*60,'reference-output':'B'*60,'session-answer':'C'*60}
        controller=FactoryOrchestrator(Path('.'),Path('unused'),ModelAgentSet(ScriptedModelProvider([])),
                                       workspace_read_manifest={})
        controller._bind_isolation_scan(SimpleNamespace(canaries=canaries),Mock())
        with patch('lightyear_factory.orchestrator.GraphContextAssembler') as assembler:
            assembler.return_value.assemble.return_value={'source_excerpts':['A'*60]}
            with self.assertRaisesRegex(ContractError,'^controller-isolation-refused$'):
                controller._context(SimpleNamespace(),Path('.'))
            assembler.return_value.assemble.return_value={'source_excerpts':['safe fixture']}
            self.assertEqual({'source_excerpts':['safe fixture']},controller._context(SimpleNamespace(),Path('.')))
        workspace=Mock(root=Path('.'));order=SimpleNamespace(allow_network=False,gates=())
        with patch('lightyear_factory.orchestrator.GateRunner') as runner:
            runner.return_value.run.return_value={'status':'passed','gates':[]}
            controller._run_gates(workspace,order)
            self.assertIs(controller.agents.isolation_scan,runner.call_args.kwargs['isolation_scan'])
        controller.agents.isolation_scan=None
        with self.assertRaisesRegex(ContractError,'^controller-isolation-scanner-required$'):
            controller._scan_controller_value('controller-context',{})

    def test_workspace_scan_reads_actual_bytes_and_names_without_public_paths(self):
        canaries={'expected-state':'A'*60,'reference-output':'B'*60,'session-answer':'C'*60}
        rows=[]
        def scanner(name,raw):
            rows.append(scan([(name,raw)],canaries,()))
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);workspace=IsolatedWorkspace(root/'source',root/'worker',('candidate',),{})
            (workspace.root/'candidate').mkdir(parents=True)
            target=workspace.root/'candidate'/'private-looking-name.txt';target.write_bytes(b'safe fixture')
            result=workspace.scan_contents(scanner,'fixture-workspace')
            self.assertEqual(1,result['files'])
            self.assertNotIn('private-looking-name',json.dumps(rows))
            target.write_bytes(b'prefix '+b'A'*60)
            with self.assertRaisesRegex(ContractError,'^workspace-isolation-refused$'):
                workspace.scan_contents(scanner,'fixture-workspace')
            target.write_bytes(b'safe fixture')
            (workspace.root/'candidate'/('B'*60)).write_bytes(b'safe fixture')
            with self.assertRaisesRegex(ContractError,'^workspace-isolation-refused$'):
                workspace.scan_contents(scanner,'fixture-workspace')

    def test_workspace_scan_refuses_unlisted_files_links_size_and_manifest_drift(self):
        from unittest.mock import Mock
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);workspace=IsolatedWorkspace(root/'source',root/'worker',('candidate',),{})
            workspace.root.mkdir();target=workspace.root/'unlisted';target.write_bytes(b'safe')
            with self.assertRaisesRegex(ContractError,'^workspace-isolation-refused$'):
                workspace.scan_contents(Mock(),'fixture')
            target.unlink();(workspace.root/'candidate').mkdir();target=workspace.root/'candidate'/'file'
            target.write_bytes(b'safe')
            with patch.object(Path,'is_symlink',return_value=True):
                with self.assertRaisesRegex(ContractError,'^workspace-isolation-refused$'):
                    workspace.scan_contents(Mock(),'fixture')
            with target.open('wb') as handle:handle.truncate(8*1024*1024+1)
            with self.assertRaisesRegex(ContractError,'^workspace-isolation-refused$'):
                workspace.scan_contents(Mock(),'fixture')
            target.write_bytes(b'safe')
            with patch.object(workspace,'verify_read_boundary',return_value={}):
                with self.assertRaisesRegex(ContractError,'^workspace-isolation-refused$'):
                    workspace.scan_contents(Mock(),'fixture')

    def test_controller_workspace_scan_reuses_bound_scanner(self):
        from unittest.mock import Mock
        from lightyear_factory.agents import ModelAgentSet
        from lightyear_factory.providers import ScriptedModelProvider
        controller=FactoryOrchestrator(Path('.'),Path('unused'),ModelAgentSet(ScriptedModelProvider([])),
                                       workspace_read_manifest={})
        controller.agents.isolation_scan=Mock();workspace=Mock()
        controller._scan_workspace(workspace,'final-candidate-package')
        workspace.scan_contents.assert_called_once_with(controller.agents.isolation_scan,'final-candidate-package')

    def test_allowlist_attempt_budget_refuses_before_run_creation(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        controller=FactoryOrchestrator(Path('.'),Path('unused'),Mock(),workspace_read_manifest={})
        with patch('lightyear_factory.orchestrator._run_id') as run_id:
            for cap in (0,4,True,'3'):
                with self.assertRaisesRegex(ContractError,'^factory-attempt-budget-refused$'):
                    controller.run(SimpleNamespace(max_attempts=cap),'fixture')
            run_id.assert_not_called()
        for cap in (1,2,3):controller._validate_attempt_budget(SimpleNamespace(max_attempts=cap))

    def test_allowlist_startup_error_has_no_private_text_or_agent_evidence(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        private='PRIVATE-FIXTURE-'+('x'*60)
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source=root/'source';source.mkdir()
            agents=Mock(name='agent-object');agents.name='fixture-agent'
            order=SimpleNamespace(max_attempts=1,allowed_paths=('candidate',),
                content_sha256='a'*64,order_id=private,to_dict=Mock(return_value={'title':private}))
            controller=FactoryOrchestrator(source,root/'runs',agents,
                workspace_read_manifest={},prepare_workspace=Mock(side_effect=RuntimeError(private)))
            with self.assertRaisesRegex(ContractError,'^factory-isolation-run-refused$'):
                controller.run(order,'fixture')
            agents.drain_evidence.assert_not_called();order.to_dict.assert_not_called()
            run=root/'runs'/'fixture'
            self.assertFalse((run/'work-order.json').exists())
            for filename in ('events.jsonl','receipt.json','summary.json'):
                self.assertNotIn(private,(run/filename).read_text())
            receipt=json.loads((run/'receipt.json').read_text())
            self.assertEqual('blocked',receipt['status'])
            self.assertFalse(receipt['qualifies_for_factory_receipt'])
            self.assertEqual(0,receipt['repair_loops'])

    def test_model_evidence_scan_refuses_before_artifact_write(self):
        from unittest.mock import Mock
        controller=FactoryOrchestrator(Path('.'),Path('unused'),Mock(),workspace_read_manifest={})
        controller.agents.drain_evidence.return_value=[{'error':'private fixture value'}]
        controller.agents.isolation_scan=Mock(side_effect=ContractError('private scanner detail'))
        artifacts=Mock();ledger=Mock()
        with self.assertRaisesRegex(ContractError,'^controller-isolation-refused$'):
            controller._record_agent_evidence(artifacts,ledger,[],'builder','implementer')
        artifacts.write.assert_not_called();ledger.append.assert_not_called()

    def test_receipt_package_refusal_follows_memory_preparation_without_publication(self):
        from unittest.mock import Mock
        from types import SimpleNamespace
        from lightyear_factory.ledger import RunLedger
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);agents=Mock();agents.name='fixture'
            agents.intelligence_summary.return_value={'mode':'fixture','calls':1}
            controller=FactoryOrchestrator(root,root,agents)
            controller.memory_store=Mock()
            order=SimpleNamespace(order_id='fixture',content_sha256='a'*64,title='fixture')
            ledger=RunLedger(root/'events.jsonl');order_events=[]
            controller.memory_store.prepare_run.side_effect=lambda *args: order_events.append('prepare-memory') or {}
            def refuse():
                order_events.append('package-recheck')
                raise ContractError('candidate-package-finalization-refused')
            with patch('lightyear_factory.orchestrator.write_json') as write:
                with self.assertRaisesRegex(ContractError,'^candidate-package-finalization-refused$'):
                    controller._finish(root,'fixture',order,'PASSED',1,'fixture',ledger,[],{}, {},
                        {'status':'passed','gates':[]},'fixture',{},candidate_package_check=refuse)
                write.assert_not_called()
            self.assertEqual(['prepare-memory','package-recheck'],order_events)
            controller.memory_store.observe_run.assert_not_called()
            controller.memory_store.publish_finalized_run.assert_not_called()

    @staticmethod
    def _memory_publication_fixture(root):
        from types import SimpleNamespace
        from lightyear_factory.memory import SemanticMemoryStore
        from lightyear_factory.contracts import canonical_hash
        order = SimpleNamespace(order_id='fixture', content_sha256='a'*64, metadata={},
            title='fixture', goal='safe fixture', graph_node_ids=(), allowed_paths=('candidate',))
        receipt = dict(run_id='fixture', work_order_sha256=order.content_sha256,
            status='passed', verification={'status':'passed','gates':[]}, attempts=1,
            changed_paths=[], ledger_head_sha256='b'*64,
            initial_snapshot_sha256='c'*64, final_snapshot_sha256='c'*64,
            factory_build_receipt={'qualifies_for_factory_receipt':True})
        # Synthetic qualification is a component boundary fixture, not signing proof.
        receipt['content_sha256'] = canonical_hash(receipt)
        store = SemanticMemoryStore(root/'memory')
        prepared = store.prepare_run(root, order, receipt, {}, [])
        return order, receipt, store, prepared

    def test_memory_preparation_is_readonly_and_final_publication_binds_receipt(self):
        from lightyear_factory.contracts import write_json, canonical_hash
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);order,receipt,store,prepared=self._memory_publication_fixture(root)
            self.assertFalse(store.root.exists());self.assertFalse((root/'receipt.json').exists())
            write_json(receipt,root/'receipt.json');scanned=[]
            decision=store.publish_finalized_run(prepared,root,order,receipt,scanned.append)
            record=json.loads(next(store.experiences_root.glob('*.json')).read_text())
            self.assertEqual('promoted-positive',decision['disposition'])
            self.assertEqual(receipt['content_sha256'],record['run_binding']['receipt_sha256'])
            self.assertEqual(receipt['ledger_head_sha256'],record['run_binding']['ledger_head_sha256'])
            self.assertEqual(canonical_hash(record,{'content_sha256'}),record['content_sha256'])
            self.assertEqual([record],scanned);self.assertTrue(store.snapshot_path.exists())
            self.assertEqual(receipt,json.loads((root/'receipt.json').read_text()))
            with self.assertRaisesRegex(ContractError,'memory-finalized-controller-publication-required'):
                store.observe_run(root,order,receipt,{},[])

    def test_memory_final_publication_refusals_write_no_experience_or_snapshot(self):
        from lightyear_factory.contracts import write_json, canonical_hash
        from unittest.mock import Mock
        for case in ('missing-receipt','blocked','unqualified','prepared-tamper','scanner-refusal','receipt-replacement'):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as d:
                root=Path(d);order,receipt,store,prepared=self._memory_publication_fixture(root)
                if case=='blocked':receipt['status']='blocked'
                if case=='unqualified':receipt['factory_build_receipt']['qualifies_for_factory_receipt']=False
                receipt['content_sha256']=canonical_hash(receipt,{'content_sha256'})
                if case!='missing-receipt':write_json(receipt,root/'receipt.json')
                if case=='prepared-tamper':prepared['record']['knowledge']['summary']='changed'
                scanner=Mock()
                if case=='scanner-refusal':scanner.side_effect=ContractError('fixture refusal')
                if case=='receipt-replacement':scanner.side_effect=lambda record: (root/'receipt.json').write_text('{}')
                with self.assertRaises((ContractError,FileNotFoundError)):
                    store.publish_finalized_run(prepared,root,order,receipt,scanner)
                self.assertFalse(store.experiences_root.exists());self.assertFalse(store.snapshot_path.exists())

    def test_deferred_memory_publication_follows_persisted_final_receipt(self):
        from unittest.mock import Mock
        from types import SimpleNamespace
        from lightyear_factory.ledger import RunLedger
        from lightyear_factory.contracts import write_json as actual_write
        for failure in (None,'receipt-scan','receipt-write','summary-write','delivery-write'):
            with self.subTest(failure=failure),tempfile.TemporaryDirectory() as d:
                root=Path(d);agents=Mock();agents.name='fixture'
                agents.intelligence_summary.return_value={'mode':'fixture','calls':0}
                controller=FactoryOrchestrator(root,root,agents);controller.memory_store=Mock()
                events=[];controller.memory_store.prepare_run.side_effect=lambda *a: events.append('prepare') or {}
                order=SimpleNamespace(order_id='fixture',content_sha256='a'*64,title='fixture')
                ledger=RunLedger(root/'events.jsonl')
                def package_check():events.append('package');return {'fixture':True}
                def publish(prepared,run_dir,order,receipt,scan_record,**kwargs):
                    self.assertEqual(receipt,json.loads((root/'receipt.json').read_text()))
                    self.assertTrue((root/'summary.json').exists());events.append('publish')
                    return {'disposition':'promoted-positive'}
                controller.memory_store.publish_finalized_run.side_effect=publish
                def write(value,path):
                    if (failure,path.name) in {('receipt-write','receipt.json'),('summary-write','summary.json'),
                                               ('delivery-write','semantic-memory-publication.json')}:
                        raise OSError('fixture write refusal')
                    events.append(path.name);actual_write(value,path)
                def scan(label,value):
                    if failure=='receipt-scan' and label=='run-receipt':raise ContractError('fixture scan refusal')
                with patch('lightyear_factory.orchestrator.write_json',side_effect=write), \
                     patch.object(controller,'_scan_controller_value',side_effect=scan):
                    args=(root,'fixture',order,'PASSED',1,'fixture',ledger,[],{}, {},
                          {'status':'passed','gates':[]},'fixture',{})
                    if failure in ('receipt-scan','receipt-write','summary-write'):
                        with self.assertRaises((ContractError,OSError)):
                            controller._finish(*args,candidate_package_check=package_check)
                        controller.memory_store.publish_finalized_run.assert_not_called()
                    else:
                        result=controller._finish(*args,candidate_package_check=package_check)
                        self.assertEqual('passed',result['status'])
                        self.assertEqual(['prepare','package','receipt.json','summary.json','publish'],events[:5])
                        self.assertEqual(result,json.loads((root/'receipt.json').read_text()))
                controller.memory_store.observe_run.assert_not_called()
