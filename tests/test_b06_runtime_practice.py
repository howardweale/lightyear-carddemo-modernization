"""Practice run preparation and owned-cleanup controls; Docker is always mocked."""
import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from tools.b06_image_artifacts import runtime_practice as p
class PracticeTests(unittest.TestCase):
 def test_prepare_has_no_docker_or_tower_and_refuses_reuse(self):
  with tempfile.TemporaryDirectory() as t:
   r=Path(t);(r/'tools/b06_image_artifacts').mkdir(parents=True);(r/'src').mkdir()
   for name in p.WORKER|p.EXTRA:
    path=r/'tools'/(name if name in p.EXTRA else 'b06_image_artifacts/'+name);path.write_text('fixture')
   with patch.object(p.subprocess,'run',side_effect=AssertionError('No subprocess permitted')):
    plan=p.prepare(r,r/'work/practice')
    self.assertFalse(plan['run_authorized']);self.assertEqual(plan['model_calls'],0)
    with self.assertRaises(ValueError):p.prepare(r,r/'work/practice')
 def test_failure_cleanup_is_ownership_checked_and_report_preserved(self):
  with tempfile.TemporaryDirectory() as t:
   r=Path(t);(r/'tools/b06_image_artifacts').mkdir(parents=True);(r/'src').mkdir()
   for name in p.WORKER|p.EXTRA:(r/'tools'/(name if name in p.EXTRA else 'b06_image_artifacts/'+name)).write_text('fixture')
   root=r/'work/practice';p.prepare(r,root);state={'created':False,'removed':False}
   def command(args,**kw):
    self.assertEqual(args[0],'docker');a=args[1:];out=b'';err=b'';code=0
    if a[:2]==['image','inspect']:out=json.dumps([dict(Id=p.IMAGE,Config={})]).encode()
    elif a[0]=='create':state.update(created=True,name=a[a.index('--name')+1],label=a[a.index('--label')+1])
    elif a[0]=='start':code=1;err=b'worker error verbatim'
    elif a[0]=='logs':err=b'worker error verbatim'
    elif a[0]=='ps' and '--filter' in a:out=b'owned' if state['created'] and not state['removed'] else b''
    elif a[:2]==['container','inspect']:out=json.dumps([dict(Name='/'+state['name'],Image=p.IMAGE,Config=dict(Labels={'lightyear.b06.practice':state['name']}))]).encode()
    elif a[0]=='rm':self.assertEqual(a,['rm','--force','owned']);state['removed']=True
    return type('Exit',(),dict(returncode=code,stdout=out,stderr=err))()
   with patch.object(p.subprocess,'run',side_effect=command):report=p.run(root/'practice-plan.json')
   self.assertTrue(report['cleanup_passed']);self.assertFalse(report['passed']);self.assertTrue(state['removed'])
   self.assertIn(b'worker error verbatim',(root/'container.log').read_bytes())
   with self.assertRaises(FileExistsError):p.run(root/'practice-plan.json')
