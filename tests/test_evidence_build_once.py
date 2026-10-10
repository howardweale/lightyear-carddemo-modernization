import copy, json, shutil, tempfile, unittest
from pathlib import Path
from lightyear_evidence.build_once import compare_package, descriptor, digest, seal, verify_seal, replay_saved

FIXTURE=Path(__file__).parent/'fixtures/build-once-public-v1'
PIN='34541294631e0020a5b864a195f0851a172f465f3c4bff9dcc4e757468fa9272'

class BuildOnceContractTests(unittest.TestCase):
 def test_public_saved_jvm_outputs_replay_without_jvm(self):
  contract=json.loads((FIXTURE/'contract.json').read_bytes())
  result=replay_saved(FIXTURE,contract,PIN)
  self.assertEqual(set(result['consumers']),{'one','two'})
  self.assertEqual((FIXTURE/'one/stdout.txt').read_bytes().strip(),b'21')
  self.assertEqual((FIXTURE/'two/stdout.txt').read_bytes().strip(),b'35')
  generation=json.loads((FIXTURE/'generation.json').read_bytes());verify_seal(generation)
  self.assertEqual(generation['shared_compilations'],1)
  for name,expected in generation['source_files'].items():self.assertEqual(descriptor((FIXTURE/name).read_bytes()),expected)
  self.assertEqual(descriptor((FIXTURE.parents[2]/'tools/build_public_consumer_fixture.py').read_bytes()),generation['generator'])
 def test_explicit_replacement_only_and_metadata_unchanged(self):
  base=dict(version='one',entries={'Main.class':descriptor(b'main'),'Probe.class':descriptor(b'one')})
  current=copy.deepcopy(base);current['entries']['Probe.class']=descriptor(b'two')
  self.assertTrue(compare_package(base,current,{'Probe.class':descriptor(b'two')}))
  self.assertEqual(base['entries']['Probe.class'],descriptor(b'one'))
  for path in ('Main.class','extra.class'):
   bad=copy.deepcopy(current);bad['entries'][path]=descriptor(b'changed')
   with self.assertRaisesRegex(ValueError,'shared-content'):compare_package(base,bad,{'Probe.class':descriptor(b'two')})
  bad=copy.deepcopy(current);bad['version']='two'
  with self.assertRaisesRegex(ValueError,'shared-content'):compare_package(base,bad,{'Probe.class':descriptor(b'two')})
 def test_missing_or_unapproved_replacement_refused(self):
  base=dict(entries={'Probe.class':descriptor(b'one')})
  for candidate in ({}, {'Probe.class':descriptor(b'other')}):
   with self.assertRaises(ValueError):compare_package(base,dict(entries=candidate),{'Probe.class':descriptor(b'two')})
 def test_manifest_digest_is_pinned_not_self_authorizing(self):
  c=json.loads((FIXTURE/'contract.json').read_bytes())
  with self.assertRaisesRegex(ValueError,'manifest-binding'):replay_saved(FIXTURE,c,'0'*64)
  c['consumers']['one']['returncode']=1
  with self.assertRaisesRegex(ValueError,'manifest-hash'):replay_saved(FIXTURE,c,PIN)
  c.pop('content_sha256');c=seal(c)
  with self.assertRaisesRegex(ValueError,'manifest-binding'):replay_saved(FIXTURE,c,PIN)
 def test_saved_bytes_and_pre_post_records_are_checked(self):
  cases=[('shared/Shared.class',b'changed'),('one/Probe.class',b'changed'),('one/stdout.txt',b'wrong'),('two/after.json',b'{}')]
  for name,raw in cases:
   with self.subTest(name=name),tempfile.TemporaryDirectory() as d:
    root=Path(d)/'fixture';shutil.copytree(FIXTURE,root);(root/name).write_bytes(raw)
    with self.assertRaises(ValueError):replay_saved(root,json.loads((root/'contract.json').read_bytes()),PIN)
 def test_resealed_execution_cannot_change_command_or_binding(self):
  for field,value in [('argv',['mvn']),('manifest_sha256','0'*64),('returncode',1),('shared_after',{}),('candidate_after',{})]:
   with self.subTest(field=field),tempfile.TemporaryDirectory() as d:
    root=Path(d)/'fixture';shutil.copytree(FIXTURE,root);p=root/'one/execution.json';v=json.loads(p.read_bytes());v.pop('content_sha256');v[field]=value;p.write_text(json.dumps(seal(v)))
    with self.assertRaises(ValueError):replay_saved(root,json.loads((root/'contract.json').read_bytes()),PIN)
 def test_contract_rejects_traversal_even_if_caller_pins_it(self):
  c=json.loads((FIXTURE/'contract.json').read_bytes());c.pop('content_sha256');c['shared_files']={'../outside':descriptor(b'')};c=seal(c)
  with self.assertRaisesRegex(ValueError,'artifact-path'):replay_saved(FIXTURE,c,c['content_sha256'])

if __name__=='__main__':unittest.main()
