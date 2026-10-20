"""CI-only existing-controller dry runs. No external model or signing authority.

The actual controller, agents, transport recorder, accounting, PatchBroker,
workspace scans, private Git history, export and computed receipt are exercised.
Admission, identity, OCI execution and signature boundaries are explicitly mocked;
passing these fixtures is not real factory acceptance or cryptographic proof.
"""
from contextlib import ExitStack, contextmanager
import hashlib
from io import BytesIO
import json
from pathlib import Path
import tempfile
import traceback
import unittest
from unittest.mock import patch

from lightyear_execution.backend import OCIContainerBackend, ExecutionResult
from lightyear_execution.contracts import ExecutionPolicy
from lightyear_execution.integration import HardenedExecutionContext
from lightyear_factory.additional_providers import AnthropicMessagesProvider
from lightyear_factory.agents import ModelAgentSet
from lightyear_factory.authorship import CandidateHistory, CICommitSigner, REF
from lightyear_factory.contracts import ContractError, WorkOrder, canonical_hash
from lightyear_factory.gates import CandidateBuildBackend
from lightyear_factory.model_admission import FactoryModelAdmission
from lightyear_factory.orchestrator import FactoryOrchestrator

ROOT=Path(__file__).resolve().parents[1]
PRIVATE='PRIVATE-EXPECTED-FIXTURE-'+'z'*64


class ControllerDryRunTests(unittest.TestCase):
    def scenario(self, mode):
        temp=self.enterContext(tempfile.TemporaryDirectory());root=Path(temp)
        source=root/'source';(source/'candidate').mkdir(parents=True)
        (source/'candidate/toy.txt').write_text('wrong0\n')
        manifest={'candidate/toy.txt':hashlib.sha256(b'wrong0\n').hexdigest()}
        order=WorkOrder.from_dict(dict(schema_version='1.0',id='fixture-order',title='Toy fixture',goal='Repair toy text',
            scope={'allowed_paths':['candidate'],'graph_node_ids':[]},
            acceptance={'max_attempts':3,'baseline_first':False,'gates':[{'id':'toy','command':['python','-c','pass']}]},
            policy={'max_model_tokens':1000000,'max_model_calls':12,'max_model_cost_usd':10,'max_elapsed_seconds':120}))
        policy=ExecutionPolicy.load(ROOT/'factory/execution/policy.json')
        execution=object.__new__(HardenedExecutionContext)
        execution.policy=policy;execution.backend=OCIContainerBackend(policy,'docker',execute=True)
        execution.work_order_sha256=order.content_sha256
        execution.admission_receipt={'content_sha256':'1'*64}
        execution.identity_receipts=[];execution.authorization_receipts=[]
        execution.execution_evidence=[];execution.secret_receipts=[]
        admission=object.__new__(FactoryModelAdmission)
        proof=dict(schema='factory-model-admission/1',plan_sha256='2'*64,decision_sha256='3'*64,
            trusted_journal_head='4'*64,executable_commit='5'*40,work_order_sha256=order.content_sha256)
        runtime=dict(proof,provider=None,model=None,role=None,provider_verified=False,workspace_read_manifest=manifest)
        def verify(current_order, provider, role):
            self.assertIs(order,current_order)
            return dict(proof,provider=provider.provider_id,model=provider.model,
                        role='analyst' if role=='failure_analyst' else role,provider_verified=True)
        responses=[];builds=[];histories=[]
        @contextmanager
        def opener(request, **kwargs):
            body=json.loads(request.data);payload=json.loads(body['messages'][0]['content'])
            schema=body['output_config']['format']['schema'];props=schema['properties']
            if 'tasks' in props:
                content={'summary':'Toy plan','tasks':[{'id':'toy','objective':'Repair toy',
                    'paths':['candidate'],'graph_node_ids':[],'evidence_capsule_ids':[]}],'risks':[]}
            elif 'edits' in props:
                attempt=payload['attempt'];builds.append(attempt)
                replacement=PRIVATE if mode=='leak' else ('fixed' if mode!='cap' and attempt==2 else 'wrong'+str(attempt))
                content={'summary':'Toy edit','edits':[{'path':'candidate/toy.txt','find':'wrong'+str(attempt-1),
                    'replace':replacement,'rationale':'Fixture change'}],'blocked_reason':None}
            else:
                content={'summary':'Toy differs','failure_codes':['value'],'builder_guidance':'Repair toy text','risk':'low'}
            envelope={'model':'fixture-2026-10-18','stop_reason':'end_turn',
                'content':[{'type':'text','text':json.dumps(content)}],'usage':{'input_tokens':12,'output_tokens':8}}
            raw=json.dumps(envelope).encode();responses.append(raw)
            with BytesIO(raw) as response:yield response
        provider=AnthropicMessagesProvider('fixture-2026-10-18',api_key='offline-fixture',
            input_usd_per_million=1,output_usd_per_million=1,max_output_tokens=256,opener=opener)
        agents=ModelAgentSet(provider)
        controller=FactoryOrchestrator(source,root/'runs',agents,workspace_read_manifest=manifest,
            execution_context=execution,model_admission=admission,private_expected_values_path=root/'not-read-private.json',
            candidate_signing_paths=(root/'not-read-key',root/'not-read-trust'),transport_encryption=(b'x'*32,'fixture-key'))
        def authorize(role,action,now):
            receipt={'role':role,'action':action};receipt['content_sha256']=canonical_hash(receipt)
            execution.authorization_receipts.append(receipt)
            return receipt
        initialize=CandidateHistory.initialize
        def remember(history):
            result=initialize(history);histories.append(history);return result
        def sign(signer,history,tree,parent,message):
            return history._git('commit-tree','--no-gpg-sign',tree,'-p',parent,data=message).decode().strip()
        def human_commit(history, text):
            target=history.workspace.root/'candidate/toy.txt';target.write_text(text)
            parent=history._git('rev-parse',REF).decode().strip()
            history._git('add','--','candidate/toy.txt');tree=history._git('write-tree').decode().strip()
            commit=history._git('commit-tree','--no-gpg-sign',tree,'-p',parent,data=b'Human fixture edit\n').decode().strip()
            history._git('update-ref',REF,commit,parent)
        def gate(backend, command, workspace, environment, timeout):
            value=(workspace/'candidate/toy.txt').read_text()
            if mode=='reverted-human' and value=='wrong1\n' and not getattr(self,'inserted_human',False):
                self.inserted_human=True;human_commit(histories[0],'human edit\n');human_commit(histories[0],value)
            passed=value=='fixed\n'
            evidence={'enforced':True,'assurance':'enforced','network_mode':'none',
                'candidate_build_root':'/tmp/factory-build','workspace_read_only':True}
            evidence['content_sha256']=canonical_hash(evidence)
            return ExecutionResult(0 if passed else 1,False,1,b'toy-pass' if passed else b'toy-difference',b'',evidence)
        with ExitStack() as stack:
            stack.enter_context(patch.object(admission,'verify',side_effect=verify))
            stack.enter_context(patch.object(admission,'verify_runtime',return_value=runtime))
            stack.enter_context(patch.object(admission,'private_expected_values',return_value=(PRIVATE,)))
            stack.enter_context(patch.object(execution,'bind',return_value={'content_sha256':'6'*64}))
            stack.enter_context(patch.object(execution,'authorize',side_effect=authorize))
            stack.enter_context(patch('lightyear_factory.orchestrator.GraphContextAssembler.assemble',return_value={'nodes':[],'source_excerpts':[]}))
            stack.enter_context(patch.object(CICommitSigner,'__init__',return_value=None))
            stack.enter_context(patch.object(CICommitSigner,'sign',sign))
            stack.enter_context(patch.object(CICommitSigner,'verify',return_value=True))
            stack.enter_context(patch.object(CandidateHistory,'initialize',remember))
            stack.enter_context(patch.object(CandidateBuildBackend,'execute',gate))
            if mode=='leak':
                with self.assertRaisesRegex(ContractError,'^factory-isolation-run-refused$'):
                    controller.run(order,'fixture-run')
                result=json.loads((root/'runs/fixture-run/receipt.json').read_text())
            else:
                try:
                    result=controller.run(order,'fixture-run')
                except ContractError as error:
                    # CI diagnostics contain code locations and types only. Never
                    # reveal exception messages, source lines, locals or payloads.
                    locations=[];seen=set();cause=error
                    while cause is not None and id(cause) not in seen:
                        seen.add(id(cause))
                        locations.append({'type':type(cause).__name__, 'frames':[
                            {'file':Path(frame.filename).name,'function':frame.name,'line':frame.lineno}
                            for frame in traceback.extract_tb(cause.__traceback__)]})
                        cause=cause.__cause__ or cause.__context__
                    raise AssertionError(json.dumps({'fixture':mode,'builds':builds,
                        'exception_locations':locations},sort_keys=True)) from None
        run=root/'runs/fixture-run'
        events=[json.loads(line) for line in (run/'events.jsonl').read_text().splitlines()]
        return result,events,builds,run

    def test_leak_blocks_before_candidate_commit_and_redacts_public_evidence(self):
        receipt,events,builds,run=self.scenario('leak')
        self.assertEqual([1],builds, 'Leak case must reach the builder response, not fail during setup')
        self.assertEqual('blocked',receipt['status'])
        self.assertFalse(receipt['qualifies_for_factory_receipt'])
        self.assertFalse(any(e['kind']=='candidate_committed' for e in events))
        for name in ('events.jsonl','receipt.json','summary.json'):
            self.assertNotIn(PRIVATE,(run/name).read_text())
        self.assertFalse((run/'candidate-package').exists())

    def test_divergence_repairs_and_passes_computed_fixture_receipt(self):
        receipt,events,builds,run=self.scenario('repair')
        self.assertEqual([1,2],builds)
        self.assertEqual('passed',receipt['status'])
        self.assertTrue(receipt['factory_build_receipt']['qualifies_for_factory_receipt'])
        self.assertEqual([],receipt['factory_build_receipt']['reasons'])
        self.assertEqual(1,receipt['repair_loops'])
        self.assertEqual('fixed\n',(run/'candidate-package/candidate/toy.txt').read_text())
        self.assertEqual(2,sum(e['kind']=='candidate_committed' for e in events))

    def test_reverted_human_edit_stays_in_history_and_blocks_acceptance(self):
        receipt,events,builds,run=self.scenario('reverted-human')
        self.assertEqual('blocked',receipt['status'])
        self.assertFalse(receipt['factory_build_receipt']['qualifies_for_factory_receipt'])
        audits=[e['payload'] for e in events if e['kind']=='candidate_authorship_audited']
        self.assertEqual(2,audits[-1]['human_interventions'])
        self.assertFalse((run/'candidate-package').exists())

    def test_attempt_cap_stops_at_three_builds_and_two_repairs(self):
        receipt,events,builds,run=self.scenario('cap')
        self.assertEqual([1,2,3],builds)
        self.assertEqual('blocked',receipt['status'])
        self.assertEqual(3,receipt['attempts']);self.assertEqual(2,receipt['repair_loops'])
        self.assertFalse(receipt['factory_build_receipt']['qualifies_for_factory_receipt'])
        self.assertEqual(1,sum(e['kind']=='attempt_budget_exhausted' for e in events))
