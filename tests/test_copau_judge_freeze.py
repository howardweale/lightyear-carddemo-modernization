import copy
from hashlib import sha256
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile
from tools.check_copau_judge_freeze import (audit, verify, amended_manifest, MANIFEST, GUARDS,
                                          AMENDMENT, L2_PATH, EXTRA_REQUIRED, JAVA_TEST_ROOT)

class JudgeFreezeTests(unittest.TestCase):
    def test_target_checker_refuses_a_head_checker_that_claims_success(self):
        files,manifest=self.fixture()
        checker=(Path(__file__).resolve().parents[1]/'tools/check_copau_judge_freeze.py').read_bytes()
        with tempfile.TemporaryDirectory() as d:
            outer=Path(d);root=outer/'candidate';root.mkdir()
            def git(*args):
                return subprocess.check_output(['git',*args],cwd=root).decode().strip()
            git('init');git('config','user.name','Fixture');git('config','user.email','fixture@example.invalid')
            for path,data in files.items():
                dest=root/path;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data)
            git('add','.');git('-c','core.hooksPath=/dev/null','commit','--no-gpg-sign','-m','source')
            manifest['source_commit']=git('rev-parse','HEAD')
            for path in GUARDS:
                dest=root/path;dest.parent.mkdir(parents=True,exist_ok=True)
                dest.write_bytes(json.dumps(manifest).encode() if path==MANIFEST else
                                 checker if path=='tools/check_copau_judge_freeze.py' else b'fixture guard')
            git('add','.');git('-c','core.hooksPath=/dev/null','commit','--no-gpg-sign','-m','trusted controls')
            base=git('rev-parse','HEAD')
            trusted=outer/'trusted_checker.py'
            trusted.write_bytes(subprocess.check_output(
                ['git','show',base+':tools/check_copau_judge_freeze.py'],cwd=root))
            marker=root/'candidate-checker-executed'
            (root/'tools/check_copau_judge_freeze.py').write_text(
                "from pathlib import Path\nPath('candidate-checker-executed').touch()\nprint('green')\n")
            git('add','.');git('-c','core.hooksPath=/dev/null','commit','--no-gpg-sign','-m','malicious checker')
            result=subprocess.run([sys.executable,'-I','-B',str(trusted),'--root',str(root),'--base',base],
                                  cwd=root,text=True,capture_output=True)
            self.assertNotEqual(0,result.returncode)
            self.assertIn('freeze-control-changed:tools/check_copau_judge_freeze.py',result.stderr)
            self.assertFalse(marker.exists())

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

    def test_amendment_bootstrap_is_main_only_and_freezes_new_bindings(self):
        files, manifest = self.fixture()
        files[L2_PATH] = b'original update edits'
        manifest['files'].append(dict(path=L2_PATH, sha256=sha256(files[L2_PATH]).hexdigest()))
        java = JAVA_TEST_ROOT + 'example/BoundaryTest.java'
        extras = {path: ('bound input ' + path).encode() for path in (*EXTRA_REQUIRED, java)}
        original = copy.deepcopy(manifest)
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            def git(*args):
                return subprocess.check_output(['git', *args], cwd=root).decode().strip()
            def write(path, raw):
                dest = root/path; dest.parent.mkdir(parents=True, exist_ok=True); dest.write_bytes(raw)
            def commit(message):
                git('add', '.')
                git('-c', 'core.hooksPath=/dev/null', 'commit', '--no-gpg-sign', '-m', message)
                return git('rev-parse', 'HEAD')
            git('init'); git('config', 'user.name', 'Fixture')
            git('config', 'user.email', 'fixture@example.invalid')
            for path, raw in files.items(): write(path, raw)
            manifest['source_commit'] = commit('original frozen source')
            changed = b'previously approved L2 update edits'
            write(L2_PATH, changed)
            for path, raw in extras.items(): write(path, raw)
            source = commit('approved L2 source and additional verifier inputs')
            raw_manifest = json.dumps(manifest).encode()
            amendment = dict(schema='copau-factory-judge-amendment/1', main_source=source,
                original_manifest_sha256=sha256(raw_manifest).hexdigest(),
                existing_authorized_change=dict(path=L2_PATH, source_commit=source,
                    old_sha256=sha256(files[L2_PATH]).hexdigest(), sha256=sha256(changed).hexdigest()),
                files=[dict(path=path, sha256=sha256(raw).hexdigest()) for path, raw in extras.items()])
            for path in GUARDS: write(path, raw_manifest if path == MANIFEST else b'trusted fixture control')
            write(AMENDMENT, json.dumps(amendment).encode())
            installed = commit('reviewed initial installation')
            env = dict(GITHUB_ACTIONS='true', GITHUB_EVENT_NAME='push', GITHUB_REF='refs/heads/main',
                       GITHUB_SHA=installed)
            with patch('tools.check_copau_judge_freeze.L2_SOURCE', source), patch.dict(os.environ, env):
                with self.assertRaisesRegex(ValueError, 'freeze-trusted-baseline-missing'):
                    audit(root, source)
                for key, value in [('GITHUB_ACTIONS', 'false'), ('GITHUB_EVENT_NAME', 'pull_request_target'),
                                   ('GITHUB_REF', 'refs/heads/candidate'), ('GITHUB_SHA', source)]:
                    with self.subTest(environment=key), patch.dict(os.environ, {key: value}):
                        with self.assertRaisesRegex(ValueError, 'freeze-bootstrap-main-only'):
                            audit(root, source, bootstrap_reviewed_main=True)
                result = audit(root, source, bootstrap_reviewed_main=True)
                self.assertEqual(source, result['recorded_L2_exception'])
                self.assertEqual(len(files) + len(extras), result['files'])
                self.assertEqual(raw_manifest, (root/MANIFEST).read_bytes())
                self.assertEqual('frozen', audit(root, installed)['state'])
                def read_source(ref, path):
                    self.assertEqual(source, ref)
                    return changed if path == L2_PATH else extras[path]
                for name in ('missing', 'duplicate', 'wrong_digest', 'wrong_old', 'other_exception'):
                    bad = copy.deepcopy(amendment)
                    if name == 'missing': bad['files'].pop()
                    elif name == 'duplicate': bad['files'].append(copy.deepcopy(bad['files'][0]))
                    elif name == 'wrong_digest': bad['files'][0]['sha256'] = '0'*64
                    elif name == 'wrong_old': bad['existing_authorized_change']['old_sha256'] = '0'*64
                    else: bad['existing_authorized_change']['path'] = 'unapproved.py'
                    with self.subTest(amendment=name), self.assertRaisesRegex(ValueError, 'freeze-amendment'):
                        amended_manifest(manifest, bad, read_source, {java})
                for path in extras:
                    write(path, extras[path] + b' tamper'); commit('candidate changes bound input')
                    with self.subTest(path=path), self.assertRaisesRegex(ValueError, 'frozen-path-changed'):
                        audit(root, installed)
                    write(path, extras[path]); commit('restore fixture input')
                added = JAVA_TEST_ROOT + 'example/UnboundTest.java'
                write(added, b'new unbound test'); commit('candidate adds unbound test')
                with self.assertRaisesRegex(ValueError, 'freeze-amendment-test-inventory-changed'):
                    audit(root, installed)
                (root/added).unlink(); commit('restore fixture inventory')
                for raw in (b'{}', None):
                    if raw is None: (root/AMENDMENT).unlink()
                    else: write(AMENDMENT, raw)
                    commit('candidate tampers with amendment')
                    with self.assertRaisesRegex(ValueError, 'freeze-control-changed'):
                        audit(root, installed)
            self.assertEqual(original['files'], manifest['files'])
