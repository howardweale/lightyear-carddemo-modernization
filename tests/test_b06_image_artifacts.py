"""Offline extraction/authorization/ownership controls. Never calls Docker."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch
import warnings
import zipfile

from lightyear_calibration.contracts import canonical, read_json, seal
from lightyear_control_tower.decisions import ZERO, verify_envelope
from lightyear_control_tower.kinds import default_registry
from lightyear_control_tower.requests import RequestInbox
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
from lightyear_workflow.campaign_engine import Signer
from tools.b06_image_artifacts import controller as c
from tools.b06_image_artifacts.extract import collect, verify_catalogue, LIMITS
from tools.b06_image_artifacts.prepare import prepare


def test_signer():
    signer=Signer.__new__(Signer)
    signer.key=Ed25519PrivateKey.generate()
    signer.public=signer.key.public_key().public_bytes(
        serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo)
    return signer


def proof(signer, bound, now, outcome='authorized'):
    actor={'id':'operator-fixture','kind':'human'}
    event=signer.sign({'sequence':1,'previous_sha256':ZERO,'kind':'tower_decision','actor':actor,
        'session_id':'test', 'payload':{'schema':'tower-decision/1','kind':c.KIND,'kind_version':1,
        'scope':c.SCOPE,'bound':bound,'outcome':outcome,'channel':'control-tower','actor':actor,
        'session_id':'test','roles_held':['campaign-authorizer'],'reason':'synthetic test only'}})
    journal=signer.sign({'record_type':'tower-journal-export/1','scope':c.SCOPE,'events':[event],
        'journal_head_sha256':event['content_sha256'],'exported_at':now.isoformat()})
    return {'schema':'tower-decision-proof/1','journal':journal,'decision_sha256':event['content_sha256']}


class ExtractionTests(unittest.TestCase):
    def test_freeze_namespace_packages_uses_exact_git_bytes_and_refuses_reuse(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo=Path(tmp);pub=repo/'public';snap=repo/'snapshot';key=repo/'tower.public.pem'
            key.write_bytes(test_signer().public)
            names=[c.EXTRACTOR,'src/fixture.py','tests/test_b06_image_artifacts.py',
                   'tools/ms94_b06_qualification_worker.py','tools/ms94_b06_admission.py']
            exact=b'# exact git fixture\r\n'
            def git(args,**kwargs):
                op=args[3:]
                if op[0]=='rev-parse':return ('a'*40+'\n').encode()
                if op[0]=='ls-tree':return ('\n'.join(names)+'\n').encode()
                self.assertEqual(op[:2],['cat-file','blob']);return exact
            with patch('tools.b06_image_artifacts.prepare.subprocess.check_output',side_effect=git):
                plan=prepare(repo,'a'*40,snap,pub,'2026-10-07T21:30:00Z',key)
                c.verify_snapshot(snap,plan)
                self.assertEqual((snap/c.EXTRACTOR).read_bytes(),exact)
                with self.assertRaisesRegex(ValueError,'already-exists'):
                    prepare(repo,'a'*40,snap,pub,'2026-10-07T21:30:00Z',key)

    def test_duplicate_jar_entries_and_origins_preserved_without_resolution_claim(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);app=p/'app';app.mkdir();jdk=p/'jdk'
            for name in ('bin/java','release','lib/modules','lib/server/libjvm.so'):
                f=jdk/name;f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes(name.encode())
            (jdk/'jmods').mkdir()
            with zipfile.ZipFile(jdk/'jmods/java.base.jmod','w') as z:
                z.writestr('classes/java/lang/invoke/InnerClassLambdaMetafactory.class',b'JDK FIXTURE')
            with warnings.catch_warnings():
                warnings.simplefilter('ignore',UserWarning)
                with zipfile.ZipFile(app/'a.jar','w') as z:
                    z.writestr('same/Name.class',b'FIRST');z.writestr('same/Name.class',b'SECOND')
            with zipfile.ZipFile(app/'b.jar','w') as z:z.writestr('same/Name.class',b'THIRD')
            (app/'copied.jar').write_bytes((app/'a.jar').read_bytes())
            with patch('subprocess.run',side_effect=AssertionError('no subprocess')):
                r=collect([app],jdk,p/'out')
            copies=[x for x in r['classes'] if x['entry']=='same/Name.class']
            self.assertEqual(len(copies),3);self.assertEqual(len({x['sha256'] for x in copies}),3)
            self.assertEqual([x['ordinal'] for x in copies],[0,1,0])
            self.assertEqual(len(copies[0]['artifact_paths']),2)
            self.assertFalse((p/'out/blobs'/copies[0]['sha256']).exists())
            self.assertTrue(verify_catalogue(p/'out',r)['full_class_bytes_replayed'])
            for field,value in [('sha256','f'*64),('ordinal',99),('artifact_paths',[])]:
                changed=json.loads(json.dumps(r));changed['classes'][0][field]=value
                with self.subTest(field=field),self.assertRaises(ValueError):verify_catalogue(p/'out',changed)
            missing=json.loads(json.dumps(r));missing['classes'].pop()
            with self.assertRaisesRegex(ValueError,'closure'):verify_catalogue(p/'out',missing)
            self.assertFalse(r['resolved_runtime_claim']);self.assertFalse(r['native_admission'])
            with self.assertRaises(FileExistsError):collect([app],jdk,p/'out')


class ControllerTests(unittest.TestCase):
    def fixture(self,tmp):
        p=Path(tmp);root=p/'snapshot';root.mkdir();out=p/'output'
        f=root/c.EXTRACTOR;f.parent.mkdir(parents=True);f.write_bytes(b'# test fixture only\n')
        core=seal({'image':c.IMAGE,'native_pairs':0,'model_calls':0,'target_jvm_executions':0,
                   'catalogue_schema':'b06-image-artifact-catalogue/2','extraction_limits':LIMITS,
                   'maximum_extraction_seconds':900,'cleanup_reserve_seconds':600,'container_count':1,'retries':0})
        (root/'core.json').write_bytes(canonical(core))
        manifest=seal({'schema':'b06-image-extraction-snapshot/1','model_calls':0,
            'files_sha256':{n:c.sha(root/n) for n in ('core.json',c.EXTRACTOR)}})
        (root/'snapshot.json').write_bytes(canonical(manifest))
        now=datetime(2026,10,8,3,0,tzinfo=timezone.utc);tower=test_signer();signer=test_signer()
        plan=seal({'id':'b06-image-test','core_sha256':core['content_sha256'],
            'snapshot_sha256':manifest['content_sha256'],'tower_public_key_sha256':hashlib.sha256(tower.public).hexdigest(),
            'window':{'not_before_utc':now.isoformat(),'deadline_utc':(now+timedelta(minutes=30)).isoformat(),
                      'latest_start_utc':(now+timedelta(minutes=5)).isoformat()}})
        reader=Mock(key=tower.public);reader.get.side_effect=lambda k,b,n:proof(tower,b,n)
        return root,out,plan,now,tower,signer,reader

    def test_inbox_and_fresh_distinct_tower_signature(self):
        with tempfile.TemporaryDirectory() as tmp:
            root,out,plan,now,tower,signer,reader=self.fixture(tmp)
            name,bound=c.write_request(tmp,plan,'a'*40)
            self.assertEqual(RequestInbox(tmp,c.SCOPE,default_registry()).item(name)['bound'],bound)
            self.assertIsNotNone(c.authorize(plan,'a'*40,reader,now,signer.public))
            for fault in ('missing','rejected','stale','campaign','changed'):
                def get(k,b,n):
                    if fault=='missing':return None
                    return proof(signer if fault=='campaign' else tower,
                        {**b,'plan':'f'*64} if fault=='changed' else b,
                        n-timedelta(minutes=2) if fault=='stale' else n,
                        'rejected' if fault=='rejected' else 'authorized')
                reader.get.side_effect=get
                with self.subTest(fault=fault),self.assertRaises(ValueError):c.authorize(plan,'a'*40,reader,now,signer.public)

    def test_no_docker_before_publication_snapshot_time_and_tower_guards(self):
        for fault in ('unpublished','changed-snapshot','late','no-decision','output-reuse'):
            with self.subTest(fault=fault),tempfile.TemporaryDirectory() as tmp:
                root,out,plan,now,tower,signer,reader=self.fixture(tmp);docker=Mock(side_effect=AssertionError('must not call Docker'))
                if fault=='changed-snapshot':(root/c.EXTRACTOR).write_bytes(b'changed')
                if fault=='late':now+=timedelta(minutes=6)
                if fault=='no-decision':reader.get.side_effect=None;reader.get.return_value=None
                if fault=='output-reuse':out.mkdir()
                with self.assertRaises(ValueError):
                    c.execute(root,plan,out,'a'*40,reader,signer,public_verified=fault!='unpublished',clock=lambda:now,docker=docker)
                docker.assert_not_called()

    def test_publication_requires_remote_identity_and_every_exact_blob(self):
        for fault in ('none','remote','blob','plan','closure'):
            with self.subTest(fault=fault),tempfile.TemporaryDirectory() as tmp:
                root,out,plan,now,tower,signer,reader=self.fixture(tmp)
                value={k:v for k,v in plan.items() if k!='content_sha256'}
                value.update({'public_plan_path':'public/plan.json',
                    'public_ref':'refs/heads/codex/b06-observer-v2-preparation',
                    'public_files':{n:'public/'+n for n in (c.EXTRACTOR,'core.json','snapshot.json')}})
                if fault=='closure':del value['public_files']['core.json']
                plan=seal(value);ref='refs/heads/codex/b06-observer-v2-preparation'
                def git(args,**kwargs):
                    op=args[3:]
                    if op[:2]==['remote','get-url']:
                        return b'https://github.com/howardweale/lightyear-carddemo-modernization.git\n'
                    if op[0]=='ls-remote':return ((('b' if fault=='remote' else 'a')*40)+'\t'+ref+'\n').encode()
                    self.assertEqual(op[:2],['cat-file','blob'])
                    name=op[2].split(':',1)[1]
                    if name=='public/plan.json':return b'changed' if fault=='plan' else canonical(plan)
                    return b'changed' if fault=='blob' else (root/name.removeprefix('public/')).read_bytes()
                with patch.object(c.subprocess,'check_output',side_effect=git):
                    if fault=='none':c.publication(tmp,root,plan,'a'*40,ref)
                    else:
                        with self.assertRaises(ValueError):c.publication(tmp,root,plan,'a'*40,ref)

    def test_execution_success_timeout_tamper_and_foreign_cleanup(self):
        for mode in ('success','timeout','foreign','tamper','anonymous-volume'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as tmp:
                root,out,plan,now,tower,signer,reader=self.fixture(tmp);calls=[];created=False;removed=False
                identity='1'*64
                info={'Id':identity,'Name':'/'+plan['id'],'Image':c.IMAGE,'Config':{'Labels':{'lightyear.b06.artifacts':plan['id']}},
                      'HostConfig':{'NetworkMode':'none','ReadonlyRootfs':True,'PortBindings':{}},'Mounts':[{},{}]}
                def docker(*args,timeout):
                    nonlocal created,removed
                    calls.append(args);raw=b''
                    if args[:2]==('image','inspect'):
                        raw=json.dumps([{'Id':c.IMAGE,'Config':{'Volumes':{'/bad':{}} if mode=='anonymous-volume' else {}}}]).encode()
                    elif args[0]=='create':created=True
                    elif args[:2]==('container','inspect'):
                        value=json.loads(json.dumps(info))
                        if args[2]==identity and mode=='foreign':value['Config']['Labels']={'lightyear.b06.artifacts':'other'}
                        value['State']={'Running':False,'ExitCode':0}
                        raw=json.dumps([value]).encode()
                    elif args[0]=='start':
                        if mode in ('timeout','foreign'):
                            raise subprocess.TimeoutExpired('docker start',900,output=b'partial output',stderr=b'partial error')
                        catalogue=out/'catalogue';(catalogue/'blobs').mkdir(parents=True)
                        blob=b'public synthetic artifact';h=hashlib.sha256(blob).hexdigest()
                        (catalogue/'blobs'/h).write_bytes(blob if mode!='tamper' else b'changed')
                        row={'sha256':h,'bytes':len(blob),'kind':'class-file','path':'/application/Test.class'}
                        (catalogue/'catalogue.json').write_bytes(canonical({'schema':'b06-image-artifact-catalogue/2',
                            'limits':LIMITS,'unique_blob_bytes':len(blob),
                            'model_calls':0,'native_pairs':0,'target_jvm_executions':0,'artifacts':[row],
                            'classes':[{'sha256':h,'bytes':len(blob),'artifact_sha256':h,
                              'artifact_paths':[row['path']],'entry':None,'ordinal':None,'kind':'class-file'}],
                            'runtime_files':[]}))
                    elif args[0]=='ps' and created and not removed:raw=identity.encode()
                    elif args[0]=='rm':self.assertEqual(args,('rm','--force',identity));removed=True
                    return subprocess.CompletedProcess(args,0,raw,b'')
                with patch.object(c.shutil,'disk_usage',return_value=Mock(free=32*1024**3)):
                    if mode=='success':
                        c.execute(root,plan,out,'a'*40,reader,signer,public_verified=True,clock=lambda:now,docker=docker)
                    else:
                        with self.assertRaisesRegex(ValueError,'failed-preserved'):
                            c.execute(root,plan,out,'a'*40,reader,signer,public_verified=True,clock=lambda:now,docker=docker)
                r=read_json(out/'report.json');self.assertTrue(verify_envelope(r,signer.public))
                self.assertEqual(r['passed'],mode=='success');self.assertTrue(r['frozen_hashes_unchanged'])
                self.assertEqual(r['owned_cleanup_verified'],mode!='foreign')
                if mode in ('timeout','foreign'):self.assertEqual((out/'timeout.stdout').read_bytes(),b'partial output')
                self.assertEqual([x for x in calls if x[0]=='rm'],[] if mode in ('foreign','anonymous-volume') else [('rm','--force',identity)])


if __name__=='__main__':unittest.main()
