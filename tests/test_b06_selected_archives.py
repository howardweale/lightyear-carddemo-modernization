import hashlib,json,subprocess,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock,patch
from lightyear_calibration.contracts import canonical,read_json,seal
from tools.b06_image_artifacts import selected_archives as worker,controller as c
import test_b06_image_artifacts as fixtures

class SelectedTests(unittest.TestCase):
    def selection(self,root):
        p=root/'a.jar';p.write_bytes(b'public archive fixture')
        return seal(dict(schema='b06-selected-runtime-archives/1',image='sha256:'+'d'*64,manifest_sha256='e'*64,
            artifacts=[dict(path='/root/.m2/a.jar',bytes=p.stat().st_size,sha256=worker.sha(p))]))

    def test_streamed_exact_copy_and_independent_tamper_detection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);spec=self.selection(root)
            with patch('subprocess.run',side_effect=AssertionError('no process')):
                result=worker.copy_selected(spec,root/'out',resolve=lambda p:root/Path(p).name)
            self.assertEqual(result['archives'],1)
            p=next((root/'out/archives').iterdir());p.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'copy-bytes'):worker.replay(spec,root/'out')

    def test_changed_source_fails_and_preserves_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);spec=self.selection(root);(root/'a.jar').write_bytes(b'x'*spec['artifacts'][0]['bytes'])
            with self.assertRaisesRegex(ValueError,'source-bytes'):worker.copy_selected(spec,root/'out',resolve=lambda p:root/Path(p).name)
            self.assertTrue((root/'out/copy-error.json').exists())
            self.assertFalse((root/'out/catalogue.json').exists())
            with self.assertRaises(FileExistsError):worker.copy_selected(spec,root/'out',resolve=lambda p:root/Path(p).name)

    def fixture(self,tmp):
        root,out,plan,now,tower,signer,reader=fixtures.ControllerTests().fixture(tmp)
        selected=self.selection(Path(tmp));operation='selected-runtime-archives'
        public={k:v for k,v in plan.items() if k!='content_sha256'};public.update(operation=operation,image=selected['image'],selection_sha256=selected['content_sha256'])
        image,extractor,entrypoint=c.profile(public)
        (root/extractor).write_bytes(b'# public worker fixture')
        (root/'tools/b06_image_artifacts/selected.json').write_bytes(canonical(selected))
        core=read_json(root/'core.json');core={k:v for k,v in core.items() if k!='content_sha256'}
        core.update(image=image,operation=operation,entrypoint=entrypoint,catalogue_schema='b06-selected-runtime-archive-copy/1',selection_sha256=selected['content_sha256'])
        core=seal(core);(root/'core.json').write_bytes(canonical(core))
        files={p.relative_to(root).as_posix():c.sha(p) for p in root.rglob('*') if p.is_file() and p.name!='snapshot.json'}
        manifest=seal(dict(schema='b06-image-extraction-snapshot/1',model_calls=0,files_sha256=files));(root/'snapshot.json').write_bytes(canonical(manifest))
        public.update(core_sha256=core['content_sha256'],snapshot_sha256=manifest['content_sha256']);plan=seal(public)
        return root,out,plan,now,tower,signer,reader,selected

    def test_actual_controller_uses_retained_image_only_after_exact_tower(self):
        with tempfile.TemporaryDirectory() as tmp:
            root,out,p,now,tower,signer,reader,spec=self.fixture(tmp);calls=[];created=False;removed=False
            def docker(*args,timeout):
                nonlocal created,removed
                calls.append(args);raw=b''
                if args[:2]==('image','inspect'):raw=json.dumps([{'Id':spec['image'],'Config':{}}]).encode()
                elif args[0]=='create':
                    created=True;self.assertIn('--read-only',args);self.assertIn(spec['image'],args)
                    self.assertIn('/extract/selected_archives.py',args);self.assertNotIn(c.IMAGE,args)
                elif args[:2]==('container','inspect'):
                    raw=json.dumps([dict(Id='owned',Name='/'+p['id'],Image=spec['image'],Config={'Labels':{'lightyear.b06.artifacts':p['id']}},
                        HostConfig={'NetworkMode':'none','ReadonlyRootfs':True},Mounts=[{},{}],State={'Running':False,'ExitCode':0})]).encode()
                elif args[0]=='start':worker.copy_selected(spec,out/'catalogue',resolve=lambda p:Path(tmp)/Path(p).name)
                elif args[0]=='ps' and created and not removed:raw=b'owned'
                elif args[0]=='rm':self.assertEqual(args,('rm','--force','owned'));removed=True
                return subprocess.CompletedProcess(args,0,raw,b'')
            with patch.object(c.shutil,'disk_usage',return_value=Mock(free=32*1024**3)):
                c.execute(root,p,out,'a'*40,reader,signer,public_verified=True,clock=lambda:now,docker=docker)
            self.assertTrue(read_json(out/'report.json')['passed']);self.assertTrue(removed)
            self.assertIn('Prerequisite only',c.request(p,'a'*40)[0]['summary'])

    def test_no_decision_means_no_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            root,out,p,now,tower,signer,reader,spec=self.fixture(tmp)
            reader.get.side_effect=None;reader.get.return_value=None;docker=Mock(side_effect=AssertionError('no Docker'))
            with self.assertRaisesRegex(ValueError,'tower-decision-required'):
                c.execute(root,p,out,'a'*40,reader,signer,public_verified=True,clock=lambda:now,docker=docker)
            docker.assert_not_called()

    def test_outside_path_and_new_image_cannot_reuse_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            root,out,p,now,tower,signer,reader,spec=self.fixture(tmp)
            bad={k:v for k,v in p.items() if k!='content_sha256'};bad['image']='sha256:'+'0'*64
            with self.assertRaisesRegex(ValueError,'extraction-only-plan'):c.verify_snapshot(root,seal(bad))
            bad={k:v for k,v in spec.items() if k!='content_sha256'};bad['artifacts']=[{**spec['artifacts'][0],'path':'/private/key.jar'}]
            with self.assertRaisesRegex(ValueError,'archive-path'):worker.validate(seal(bad))
    def test_freeze_selected_mode_copies_exact_committed_selection(self):
        from tools.b06_image_artifacts.prepare import prepare
        from test_b06_image_artifacts import test_signer
        with tempfile.TemporaryDirectory() as tmp:
            repo=Path(tmp);selection=self.selection(repo);key=repo/'key.pem';key.write_bytes(test_signer().public)
            selected_path='public/selected.json'
            names=[c.EXTRACTOR,'tools/b06_image_artifacts/selected_archives.py','src/fixture.py',
                'tests/test_b06_image_artifacts.py','tools/ms94_b06_qualification_worker.py','tools/ms94_b06_admission.py',selected_path]
            def git(args,**kw):
                op=args[3:]
                if op[0]=='rev-parse':return ('a'*40+'\n').encode()
                if op[0]=='ls-tree':return ('\n'.join(names)+'\n').encode()
                return canonical(selection) if op[2].endswith(':'+selected_path) else b'# committed fixture\n'
            with patch('tools.b06_image_artifacts.prepare.subprocess.check_output',side_effect=git):
                plan=prepare(repo,'a'*40,repo/'freeze',repo/'proposal','2026-10-09T00:00:00Z',key,selection_path=selected_path)
            c.verify_snapshot(repo/'freeze',plan)
            self.assertEqual(plan['operation'],'selected-runtime-archives')
            self.assertEqual(plan['image'],selection['image'])
            self.assertEqual((repo/'freeze/tools/b06_image_artifacts/selected.json').read_bytes(),canonical(selection))