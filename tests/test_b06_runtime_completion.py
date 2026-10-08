"""Offline runtime-launch admission and modifier-proposal adversaries."""
import copy,hashlib,tempfile,unittest
from pathlib import Path
from unittest.mock import patch,Mock
from lightyear_calibration.contracts import seal,digest
from tools.b06_image_artifacts import runtime_launch as launch

class RuntimeCompletionTests(unittest.TestCase):
 def test_invalid_plan_never_reaches_publication_tower_or_docker(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp); plan=seal(dict(schema='b06-runtime-closure-plan/1',image=launch.IMAGE,
       model_calls=1,native_pairs=0,database_containers=0))
   with patch.object(launch,'publication') as publish,patch.object(launch.subprocess,'run') as run:
    with self.assertRaises(Exception):launch.execute(root,root,plan,root/'out','a'*40,Mock(),Mock())
    publish.assert_not_called();run.assert_not_called()

 def test_missing_or_mutated_worker_refuses_snapshot(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);files={}
   from tools.b06_image_artifacts import runtime_producer
   for name in launch.REQUIRED:
    raw=Path(launch.__file__).read_bytes() if name=='runtime_launch.py' else (
       Path(runtime_producer.__file__).read_bytes() if name=='runtime_producer.py' else (Path(launch.__file__).parents[1].joinpath(name).read_bytes() if name=='ms94_b06_observed_worker.py' else b'bound worker'))
    (root/name).write_bytes(raw);files[name]=hashlib.sha256(raw).hexdigest()
   plan=seal(dict(schema='b06-runtime-closure-plan/1',image=launch.IMAGE,model_calls=0,native_pairs=0,
     database_containers=0,retries=0,network='none',maximum_runtime_seconds=3000,cleanup_reserve_seconds=600,
     files_sha256=files,snapshot_sha256=digest(files),measured_maven_arguments=__import__('tools.ms94_b06_observed_worker',fromlist=['maven_arguments']).maven_arguments()))
   self.assertEqual(launch.validate(root,plan),root.resolve())
   (root/'RuntimeClosureAgent.java').write_bytes(b'changed')
   with self.assertRaisesRegex(Exception,'snapshot-changed'):launch.validate(root,plan)

 def test_modifier_proposal_rejects_other_high_bits_hosts_and_methods(self):
  from tools.b06_host_probe.pool_proposal_v2 import reviewed_host_modifiers
  observed=[dict(name='m',signature='()V',modifiers=-268431350)]
  exact='ae8b6f3bd6318a3b4d506b55d7f9a9abebe9cc0cae7e160caf184ce5e21c89e5'
  with patch('tools.b06_host_probe.pool_analysis.method_flags',return_value={'m()V':0x100a}),patch(
       'tools.b06_host_probe.pool_proposal_v2.hashlib.sha256',return_value=Mock(hexdigest=lambda:exact)):
   result,changes=reviewed_host_modifiers(b'fixture',observed)
   self.assertEqual(result[0]['modifiers'],0x100a);self.assertEqual(len(changes),1)
   changed=copy.deepcopy(observed);changed[0]['modifiers']=0xe000100a
   with self.assertRaises(ValueError):reviewed_host_modifiers(b'fixture',changed)
  with patch('tools.b06_host_probe.pool_analysis.method_flags',return_value={'m()V':0x100a}):
   self.assertEqual(reviewed_host_modifiers(b'another byte-bound host',observed)[0][0]['modifiers'],0x100a)

 def test_default_interface_does_not_invent_overpasses_or_override_class_methods(self):
  from b06_synthetic_classfiles import pool_builder,u2
  from tools.b06_host_probe.pool_proposal_v2 import expected_methods
  def klass(name,interface=False,parents=(),methods=()):
   entries,put,utf,cls=pool_builder();this=cls(name);parent=cls('java/lang/Object') if name!='java/lang/Object' else 0
   interfaces=[cls(p) for p in parents];data=b''
   for method,flags in methods:
    data+=u2(flags)+u2(utf(method))+u2(utf('()V'))+u2(0)
   return (bytes.fromhex('cafebabe')+u2(0)+u2(52)+u2(len(entries)+1)+b''.join(entries)+u2(0x601 if interface else 0x421)+
       u2(this)+u2(parent)+u2(len(interfaces))+b''.join(u2(i) for i in interfaces)+u2(0)+u2(len(methods))+data+u2(0))
  closure={'java/lang/Object':klass('java/lang/Object'),'I':klass('I',True,methods=[('run',0x401),('helper',1)])}
  root=klass('Root',parents=['I'])
  self.assertEqual(expected_methods(root,closure)[1],[('run','()V')])
  self.assertEqual(expected_methods(klass('Root',parents=['I'],methods=[('run',0x401)]),closure)[1],[])
  closure['J']=klass('J',True,parents=['I'],methods=[('run',1)])
  self.assertEqual(expected_methods(klass('Root',parents=['J']),closure)[1],[])
