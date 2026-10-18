import copy
from hashlib import sha256
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import zipfile
from tools.check_copau_judge_freeze import audit,verify,MANIFEST,GUARDS

class JudgeFreezeTests(unittest.TestCase):
    def fixture(self):
        paths=['src/lightyear_data/carddemo/reference_screens.py','factory/carddemo-web/runtime/prove_slice.py',
               'src/lightyear_data/carddemo/screens.py','src/lightyear_data/carddemo/codec.py',
               'factory/copau/judge/mutation-policy.json','factory/copau/judge/service-pom.xml',
               'docs/factory/copau-factory-scope-2026-10-18.json']
        files={p:b'fixture only' for p in paths};stream=io.BytesIO()
        with zipfile.ZipFile(stream,'w') as z:z.writestr('reference/cases.json',b'fixture expected state')
        files['evidence.zip']=stream.getvalue()
        manifest=dict(schema='copau-factory-judge-freeze/1',source_commit='a'*40,
            files=[dict(path=p,sha256=sha256(v).hexdigest()) for p,v in files.items()],
            expected_state_members=[dict(archive='evidence.zip',path='reference/cases.json',sha256=sha256(b'fixture expected state').hexdigest())])
        return files,manifest

    def test_all_frozen_classes_reject_changed_bytes(self):
        files,manifest=self.fixture();self.assertEqual(8,verify(manifest,files.__getitem__)['files'])
        for path in files:
            changed=dict(files);changed[path]+=b' changed'
            with self.assertRaisesRegex(ValueError,'frozen-path-changed'):verify(manifest,changed.__getitem__)
        bad=copy.deepcopy(manifest);bad['expected_state_members'][0]['sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'expected-state-changed'):verify(bad,files.__getitem__)
        bad=copy.deepcopy(manifest);bad['files']=bad['files'][1:]
        with self.assertRaisesRegex(ValueError,'incomplete-inventory'):verify(bad,files.__getitem__)

    def test_baseline_prevents_manifest_or_guard_rewrite_and_deletion(self):
        files,manifest=self.fixture()
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            def git(*args):return subprocess.check_output(['git',*args],cwd=root).decode().strip()
            git('init');git('config','user.name','Fixture');git('config','user.email','fixture@example.invalid')
            for p,data in files.items():
                target=root/p;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
            git('add','.');git('-c','core.hooksPath=/dev/null','commit','--no-gpg-sign','-m','fixture source')
            manifest['source_commit']=git('rev-parse','HEAD')
            for p in GUARDS:
                target=root/p;target.parent.mkdir(parents=True,exist_ok=True)
                target.write_text(json.dumps(manifest) if p==MANIFEST else 'fixture guard')
            git('add','.');git('-c','core.hooksPath=/dev/null','commit','--no-gpg-sign','-m','fixture freeze')
            base=git('rev-parse','HEAD');self.assertEqual('frozen',audit(root,base)['state'])
            for path in GUARDS:
                old=(root/path).read_bytes();(root/path).write_bytes(b'weakened')
                git('add','.');git('-c','core.hooksPath=/dev/null','commit','--no-gpg-sign','-m','fixture tamper')
                with self.assertRaisesRegex(ValueError,'freeze-control-changed'):audit(root,base)
                (root/path).write_bytes(old);git('add','.');git('-c','core.hooksPath=/dev/null','commit','--no-gpg-sign','-m','restore fixture')
            (root/MANIFEST).unlink();git('add','.');git('-c','core.hooksPath=/dev/null','commit','--no-gpg-sign','-m','fixture deletion')
            with self.assertRaisesRegex(ValueError,'freeze-control-changed'):audit(root,base)
