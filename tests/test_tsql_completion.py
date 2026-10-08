import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from datetime import datetime,timezone
from lightyear_data.tsql_procedures.native_evidence import canonical,sha
from lightyear_data.tsql_procedures.dependencies import assess,capture
from lightyear_data.tsql_procedures.comparison_policy import prepare,replay,observable_equal,multiset_equal
from lightyear_data.tsql_procedures.typed_corpus import build

class CompletionTests(unittest.TestCase):
 def record(self,**changes):
  body=dict(schema='tsql-native-dependencies/1',engine='sqlserver',modules=[[1,'dbo','p','P','CREATE PROCEDURE dbo.p AS SELECT 1;']],edges=[],synonyms=[])
  body.update(changes);return dict(body,content_sha256=sha(canonical(body)))
 def test_dependency_closure_refuses_missing_dynamic_external_and_synonyms(self):
  self.assertTrue(assess(self.record())['closed'])
  for change in [dict(modules=[[1,'dbo','p','P',None]]),dict(modules=[[1,'dbo','p','P',"EXEC('SELECT 1')"]]),
    dict(edges=[[1,None,None,'other','dbo','p',False,False,False]]),dict(edges=[[1,None,None,None,'dbo','p',True,False,False]]),
    dict(synonyms=[[2,'dbo','alias','other.dbo.p']])]:
   self.assertFalse(assess(self.record(**change))['closed'])
  altered=self.record();altered['modules'][0][-1]='changed'
  with self.assertRaisesRegex(ValueError,'binding'):assess(altered)
 def test_all_module_queries_are_observed(self):
  with patch('lightyear_data.tsql_procedures.dependencies.query',return_value=[]) as q:
   capture(None,'sqlserver');self.assertEqual(q.call_count,4)
  with patch('lightyear_data.tsql_procedures.dependencies.query',return_value=[]) as q:
   capture(None,'postgresql');self.assertEqual(q.call_count,4)
 def test_tower_policy_is_bound_and_replayed_not_self_approved(self):
  policy=dict(schema='tsql-float-tolerance/1',absolute_tolerance=0.001,relative_tolerance=0)
  args=dict(scope='test',head='a'*64,now=datetime.now(timezone.utc),bound_context=dict(inventory={},procedure={},evidence={}))
  with self.assertRaises(ValueError):prepare(dict(policy=policy,proof={}),b'bad',sha(b'bad'),**args)
  with patch('lightyear_data.tsql_procedures.comparison_policy.admit',side_effect=lambda proof,key,bound,**kw: {'verified':'synthetic','bound':copy.deepcopy(bound)}) as admit:
   record=prepare(dict(policy=policy,proof={}),b'test-key',sha(b'test-key'),**args)
   self.assertEqual(replay(record),policy);self.assertEqual(admit.call_count,2)
   record['policy']['absolute_tolerance']=1
   with self.assertRaises(ValueError):replay(record)
 def test_tolerance_is_not_rounding_or_greedy_pairing(self):
  policy=dict(schema='tsql-float-tolerance/1',absolute_tolerance=1,relative_tolerance=0)
  f=lambda n:dict(type='binary-float',value=float(n).hex())
  self.assertTrue(multiset_equal([[f(1)],[f(0)]],[[f(0)],[f(2)]],policy))
  self.assertFalse(multiset_equal([[f(0)],[f(0)]],[[f(0)],[f(2)]],policy))
  self.assertFalse(observable_equal('return_code',f(0),f(0.1),policy))
 def test_all_prospective_procedures_have_named_input_and_unique_rpc(self):
  root=Path(__file__).resolve().parents[1];files=build(root)
  corpus=json.loads(files['data-modernization/tsql-procedures/typed-corpus-r1/corpus.json'])
  self.assertEqual(len(corpus['procedures']),43)
  targets=[]
  for item in corpus['procedures']:
   self.assertTrue(all(c['parameters'] for c in item['cases']),item['id'])
   targets.append(item['calling_convention']['source'])
   self.assertTrue(item['calling_convention']['target_parameters'])
   for asset in item['assets'].values():self.assertEqual(sha(files[asset['path']]),asset['sha256'])
  self.assertEqual(len(set(targets)),43)
  notice=files['data-modernization/tsql-procedures/typed-corpus-r1/informational-raiserror/correct.sql'].decode()
  self.assertNotIn(b"RAISE EXCEPTION input_value", files['data-modernization/tsql-procedures/typed-corpus-r1/informational-raiserror/wrong.sql'])
  self.assertIn("RAISE NOTICE '%', input_value;",notice)

 def test_scriptdom_type_spacing_is_normalized_for_driver_only(self):
  from lightyear_data.tsql_procedures.invocation import driver_type
  self.assertEqual(driver_type('VARCHAR (200)'),'varchar(200)')
  self.assertEqual(driver_type('DATETIME2'),'datetime2')
  self.assertEqual(driver_type('DECIMAL (10, 5)'),'decimal(10,5)')
  with self.assertRaises(ValueError):driver_type('int; SELECT 1')

 def test_input_and_null_output_contract(self):
  from lightyear_data.tsql_procedures.invocation import validate_target_arguments
  convention=dict(target_parameters=['input_value'],output_mapping={'answer':'answer'})
  self.assertEqual(validate_target_arguments(convention,dict(input_value=7,answer=None)),['input_value'])
  for args in [dict(input_value=7,answer=9),dict(input_value=7,other=None),dict(answer=None)]:
   with self.assertRaises(ValueError):validate_target_arguments(convention,args)

 def test_finalization_binds_cases_not_display_labels(self):
  from lightyear_data.tsql_procedures.m0_v3 import accept
  from lightyear_data.tsql_procedures.native_evidence import sign
  from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
  from cryptography.hazmat.primitives import serialization
  key=Ed25519PrivateKey.generate();public=key.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);items=[];records=[]
   for i in range(43):
    items.append(dict(id='p'+str(i),trap_family=i%26+1,assets={'source':{'sha256':str(i)}},calling_convention={'mode':'fixture'},
      cases=[dict(parameters={'x':i},repeated_runs=1)],expected={'policy_required':False}))
   corpus={'procedures':items};(root/'corpus.json').write_bytes(canonical(corpus))
   plan=dict(ids=[i['id'] for i in items],variants=['correct','wrong'],corpus_sha256=sha((root/'corpus.json').read_bytes()))
   (root/'plan.json').write_bytes(canonical(plan))
   for i in items:
    for variant in ('correct','wrong'):
     index=len(records)+1;params=i['cases'][0]['parameters'];case=dict(parameters=params,case_sha256=sha(canonical(params)))
     record=dict(index=index,id=i['id'],variant=variant,repeat=1,scenario='display-label:duplicated:duplicated',case_sha256=case['case_sha256'])
     folder=root/('pair-%03d-%s-%s-1'%(index,i['id'],variant));folder.mkdir()
     manifest=sign(dict(record,plan_sha256=sha((root/'plan.json').read_bytes()),assets=i['assets']),key)
     (folder/'manifest.json').write_bytes(canonical(manifest));record['manifest_sha256']=manifest['content_sha256'];records.append(record)
     for lane in ('source','target'):(folder/(lane+'.json')).write_bytes(canonical(dict(observation=dict(case_binding=case,coverage={}),reset={'reset_elapsed_seconds':1})))
   def replay(folder,*args):
    variant=folder.name.split('-')[-2]
    return {'comparison':dict(mapping={'calling_convention':{'mode':'fixture'}},coverage_qualification={'passed':True},
      differences=[{'observable':'different'}] if variant=='wrong' else [],unresolved=[],verdict='divergent' if variant=='wrong' else 'equivalent')}
   with patch('lightyear_data.tsql_procedures.m0_v3.replay_pair',side_effect=replay),patch('lightyear_data.tsql_procedures.m0_v3.coverage_union',return_value={'eligible':True}):
    self.assertTrue(accept(root,corpus,plan,records,public)['passed'])
    changed=copy.deepcopy(records);changed[0]['scenario']='changed without matching signature'
    with self.assertRaisesRegex(ValueError,'record-binding'):accept(root,corpus,plan,changed,public)
    with self.assertRaisesRegex(ValueError,'case-closure'):accept(root,corpus,plan,records[:-1],public)
    with self.assertRaisesRegex(ValueError,'case-closure'):accept(root,corpus,plan,records+[records[0]],public)
