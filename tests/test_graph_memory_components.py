"""Synthetic execution only: no embedding or language model is loaded."""
import copy
import hashlib
import importlib.util
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from lightyear_control_tower.decisions import digest
from lightyear_factory.benchmark import benchmark_work_order
from lightyear_factory.contracts import ContractError, canonical_hash
from lightyear_factory.escalation import EvaluationLadder, replay_call
from lightyear_factory.routing_policy import compile_policy
from lightyear_knowledge_graph.hybrid import build_index, search
from lightyear_knowledge_graph.local_onnx import LocalOnnxEmbedding
from lightyear_knowledge_graph.search_benchmark import evaluate
from test_graph_memory_routing import FakeProvider, SCHEMA, hashed


class ComponentTests(unittest.TestCase):
    @unittest.skipUnless(importlib.util.find_spec('numpy'), 'optional graph-embeddings NumPy dependency')
    def test_local_onnx_assets_before_load_and_masked_pooling(self):
        import numpy as np
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            files = {'model.onnx': b'synthetic', 'tokenizer.json': b'{}'}
            for name, raw in files.items(): (root / name).write_bytes(raw)
            manifest = dict(schema='local-embedding-assets/1', pooling='attention-mask-mean-l2',
                            max_tokens=256, files={n:hashlib.sha256(r).hexdigest() for n,r in files.items()})
            tokenizer = Mock()
            tokenizer.encode_batch.return_value = [SimpleNamespace(ids=[1,2], attention_mask=[1,0], type_ids=[0,0])]
            session = Mock()
            session.get_inputs.return_value = [SimpleNamespace(name=n) for n in ('input_ids','attention_mask')]
            session.run.return_value = [np.array([[[3.,4.],[100.,100.]]])]
            factory = Mock(return_value=session)
            provider = LocalOnnxEmbedding(root,manifest,session_factory=factory,
                                           tokenizer_factory=lambda raw:tokenizer)
            self.assertEqual(provider.embed(['public synthetic text']), [[.6,.8]])
            factory.assert_called_once_with(b'synthetic')
            (root/'model.onnx').write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'hash'):
                LocalOnnxEmbedding(root,manifest,session_factory=factory)
            self.assertEqual(factory.call_count,1)

    def test_embedding_corrupt_assets_refused_before_optional_runtime_import(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'model.onnx').write_bytes(b'wrong')
            manifest=dict(schema='local-embedding-assets/1',pooling='attention-mask-mean-l2',max_tokens=256,
                          files={'model.onnx':'a'*64,'tokenizer.json':'b'*64})
            factory=Mock()
            with self.assertRaisesRegex(ValueError,'hash'):LocalOnnxEmbedding(root,manifest,session_factory=factory)
            factory.assert_not_called()

    def test_literals_top_k_and_only_source_derived_abbreviations(self):
        p = dict(mode='public', customer_id='public', edges=[], nodes=[
            dict(id='a',kind='field',name='AMT',source=[dict(path='x',line_start=1,line_end=1,text='      *> amount (AMT)')]),
            dict(id='b',kind='field',name='AMT-TOTAL'),
            dict(id='c',kind='literal',name='AMT'),dict(id='d',kind='field',name='15')])
        p['search_index']=build_index(p)
        self.assertEqual(p['search_index']['abbreviations'],{})
        self.assertEqual({r['id'] for r in p['search_index']['documents']},{'a','b'})
        self.assertEqual(len(search(p,'amount',top_k=1)),1)
        self.assertEqual(search(p,'monthly interest on account balance'),[])
        with self.assertRaises(ValueError):search(p,'amount',top_k=0)

    def test_secret_broker_lease_no_environment_fallback(self):
        from lightyear_factory.provider_secrets import HardenedSecretStore
        from lightyear_factory.model_config import configured_models
        context=Mock();context.lease_secret.return_value='test-secret'
        store=HardenedSecretStore(context)
        self.assertEqual(store.read('OPENAI_API_KEY'),'test-secret')
        self.assertEqual(context.lease_secret.call_args.args[:2],('provider','OPENAI_API_KEY'))
        with self.assertRaises(ValueError):store.read('UNSCOPED_SECRET')
        config=dict(models={'x':dict(provider='openai',model='test-2026-10-07',input_usd_per_million=1,
                                     output_usd_per_million=1,max_output_tokens=10)})
        context.lease_secret.side_effect=PermissionError('not admitted')
        with patch.dict('os.environ',{'OPENAI_API_KEY':'must-not-be-used'}):
            with self.assertRaises(PermissionError):configured_models(config,secret_store=store)

    def matrix(self,n=100):
        rows=[]
        for model,cost in [('cheap',1),('strong',2)]:
            for workload in ('INTCALC','POSTTRAN','CREASTMT','ACCTPL1'):
                rows.append(dict(task_type='implement',model=model,model_version=model+'-v1',workload=workload,
                    run_count=n,passed=n,runs=[f'{model}/{workload}/{i}' for i in range(n)],
                    pair_ids=[str(i) for i in range(n)],paired_outcomes={str(i):True for i in range(n)},false_acceptances=0,cost_per_verified_task=cost))
        return hashed(dict(schema='factory-evaluation-matrix/1',false_acceptances=0,cells=rows))

    def test_compiler_wilson_sample_floor_pairing_and_no_false_accepts(self):
        policy=compile_policy(self.matrix(),margin=.1)
        self.assertEqual(policy['routes']['implement']['primary'],'cheap')
        # Even perfect 10/10 does not clear a 90% lower-bound rule.
        with self.assertRaisesRegex(ValueError,'floor'):compile_policy(self.matrix(10),margin=.1)
        self.assertEqual(compile_policy(self.matrix(35),margin=.1)['routes']['implement']['primary'],'cheap')
        with self.assertRaisesRegex(ValueError,'floor'):compile_policy(self.matrix(9),margin=.1)
        matrix=self.matrix();matrix['cells'][0]['pair_ids'][0]='different'
        matrix=hashed({k:v for k,v in matrix.items() if k!='content_sha256'})
        with self.assertRaisesRegex(ValueError,'unpaired'):compile_policy(matrix,margin=.1)
        matrix=self.matrix();matrix['false_acceptances']=1
        matrix=hashed({k:v for k,v in matrix.items() if k!='content_sha256'})
        with self.assertRaisesRegex(ValueError,'false'):compile_policy(matrix,margin=.1)

    def test_ladder_budget_closed_failure_versions_and_replay(self):
        providers={m:FakeProvider(m+'-v1') for m in ('cheap','strong')}
        declaration=dict(schema='factory-escalation-arm/1',first='cheap',repair='strong',
                         model_versions={m:p.model for m,p in providers.items()},max_builder_attempts=2)
        ladder=EvaluationLadder(providers,declaration)
        order=replace(benchmark_work_order('rounding-mode'),max_attempts=2)
        b=ladder.bind_order(order)
        b.complete('planner','',{},SCHEMA);b.complete('builder','',{},SCHEMA)
        with self.assertRaisesRegex(ContractError,'diagnostic'):b.complete('builder','',{},SCHEMA)
        b.complete('builder','',{'public_failure':{'category':'closed'}},SCHEMA)
        self.assertEqual([c['model'] for c in b.calls],['cheap-v1','cheap-v1','strong-v1'])
        count=0
        for call in b.calls:count=replay_call(call,declaration,count)
        self.assertEqual(count,2)
        with self.assertRaisesRegex(ContractError,'exhausted'):b.complete('builder','',{'public_failure':True},SCHEMA)
        providers['strong'].model='changed'
        with self.assertRaisesRegex(ContractError,'version'):ladder.bind_order(order).complete('planner','',{},SCHEMA)
        providers['strong'].model='strong-v1'
        limited=ladder.bind_order(replace(order,max_model_calls=1))
        limited.complete('builder','',{},SCHEMA)
        with self.assertRaises(ContractError):limited.complete('builder','',{'public_failure':True},SCHEMA)
        forged=copy.deepcopy(b.calls[-1]);forged['escalation']['model']='cheap'
        with self.assertRaises(ContractError):replay_call(forged,declaration,1)

    def test_benchmark_separate_authorship_bound_labels_and_margin(self):
        labels=[dict(id=str(i),relevant_ids=['a']) for i in range(75)]
        plan=dict(label_author='external-reviewer',search_tuner='implementation',query_count=75,
                  labels_sha256=digest(labels),minimum_recall5_gain=.05)
        miss={str(i):['b'] for i in range(75)};hit={str(i):['a'] for i in range(75)}
        self.assertTrue(evaluate(plan,labels,miss,hit)['measured_gain_eligible'])
        self.assertFalse(evaluate(plan,labels,miss,hit)['promote_hybrid'])
        self.assertFalse(evaluate(plan,labels,hit,hit)['promote_hybrid'])
        with self.assertRaises(ValueError):evaluate({**plan,'label_author':'implementation'},labels,miss,hit)
        with self.assertRaises(ValueError):evaluate(plan,labels[:-1],miss,hit)

    def test_first_attempt_is_task_independent_and_bound_to_receipt(self):
        from lightyear_factory.evaluation_matrix import aggregate
        call=hashed(dict(model='test',input_tokens=1,output_tokens=1,estimated_cost_usd=.01))
        for task in ('implement','repair-from-closed-diagnostic'):
            run=hashed(dict(status='passed',attempts=1,started_at='2026-10-07T00:00:00+00:00',
                completed_at='2026-10-07T00:00:01+00:00',intelligence=dict(calls=1,call_evidence_sha256=[call['content_sha256']])))
            result=dict(receipt_sha256=run['content_sha256'],status='passed',attempts=1,false_acceptance=False,case_ref='a')
            ev=hashed(dict(catalog_sha256='a'*64,evaluation_class='public-calibration',workload_id='INTCALC',
                results=[result],false_acceptances=0,totals=dict(input_tokens=1,output_tokens=1,estimated_cost_usd=.01)))
            plan=dict(cells=[dict(catalog_sha256='a'*64,evaluation_class='public-calibration',workload='INTCALC',model='test',task_type=task)])
            cell=dict(evaluation=ev,runs=[run],model_calls=[call])
            self.assertEqual(aggregate(plan,[cell])['cells'][0]['first_attempt_pass'],1)
            ev['results'][0]['attempts']=2;ev=hashed({k:v for k,v in ev.items() if k!='content_sha256'})
            with self.assertRaisesRegex(ContractError,'attempt'):aggregate(plan,[{**cell,'evaluation':ev}])


class SecondReviewComponentTests(unittest.TestCase):
    def test_snapshot_alias_and_response_drift_are_refused(self):
        from lightyear_factory.model_versions import require_snapshot,verify_response
        for alias in ('latest','gpt-6','model-2026-02-30'):
            with self.assertRaises(ValueError):require_snapshot(alias)
        p=SimpleNamespace(model='test-2026-10-01',provider_id='openai-responses',require_snapshot_response=True)
        verify_response(p,{'model':p.model})
        for response in ({},{'model':'test-2026-10-02'}):
            with self.assertRaises(ValueError):verify_response(p,response)
        p.provider_id='gemini-generate-content';verify_response(p,{'modelVersion':p.model})

    def test_abbreviations_are_not_arbitrary_subsequences_and_headers_are_dropped(self):
        p=dict(mode='public',customer_id='public',nodes=[dict(id='a',kind='field',name='PROC-COUNT'),
            dict(id='b',kind='paragraph',name='PROCESSING'),dict(id='c',kind='field',name='NEXT'),
            dict(id='d',kind='field',name='NOEXTENDED'),dict(id='e',kind='paragraph',name='PROGRAM-ID')],edges=[])
        index=build_index(p)
        self.assertEqual(index['abbreviations'],{})
        self.assertNotIn('next',index['abbreviations'])
        self.assertNotIn('e',{d['id'] for d in index['documents']})

    def test_benchmark_computes_both_rankings_and_binds_label_owner(self):
        from lightyear_knowledge_graph.search_benchmark import run
        provider=SimpleNamespace(provider_id='synthetic-local',version='hash-bound',local=True,embed=lambda texts:[[1.] for _ in texts])
        projection=dict(mode='public',customer_id='public',nodes=[dict(id='a',kind='field',name='AMOUNT')],edges=[])
        labels=[dict(id=str(i),query='amount',relevant_ids=['a']) for i in range(50)]
        plan=dict(label_author='label-owner',search_tuner='tuner',query_count=50,labels_sha256=digest(labels),
                  projection_sha256=digest(projection),provider=dict(id=provider.provider_id,version=provider.version),minimum_recall5_gain=.05)
        with patch('lightyear_factory.knowledge_trust.approve',return_value={'named_owner':'label-owner'}) as verify:
            result=run(plan,labels,projection,provider,{'signed':'synthetic'}, {})
            self.assertEqual(result['keyword']['recall_at_5'],1)
            self.assertEqual(len(result['rankings_sha256']),2)
            self.assertFalse(result['promote_hybrid'])
            verify.assert_called_once()
        with patch('lightyear_factory.knowledge_trust.approve',return_value={'named_owner':'tuner'}):
            with self.assertRaisesRegex(ValueError,'owner'):run(plan,labels,projection,provider,{}, {})


class SnapshotProviderBoundaryTests(unittest.TestCase):
    def test_raw_response_identity_required_without_changing_historical_provider(self):
        from io import BytesIO
        import json
        from lightyear_factory.model_versions import SnapshotOpenAIResponsesProvider
        from lightyear_factory.contracts import ContractError
        model='test-2026-10-01'
        for actual in (model, 'test-2026-09-01', None):
            with self.subTest(actual=actual):
                payload={'output':[{'content':[{'type':'output_text','text':'{}'}]}]}
                if actual is not None:payload['model']=actual
                provider=SnapshotOpenAIResponsesProvider('unit-not-a-key',model=model,
                    token_preflight=False,max_retries=0,
                    opener=lambda *a,**k:BytesIO(json.dumps(payload).encode()))
                if actual==model:
                    self.assertEqual({},provider.complete('builder','unit',{}, {'type':'object'}).content)
                else:
                    with self.assertRaises(ContractError):
                        provider.complete('builder','unit',{}, {'type':'object'})
