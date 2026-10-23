"""Disposable synthetic seeds only; Windows ACLs exercised on the actual runner."""
from contextlib import redirect_stdout, redirect_stderr
from copy import deepcopy
import base64
import io
import json
import logging
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from tools import copau_seed_custody as seed
from tools import copau_private_prerequisites as custody
from tools import copau_answer_key as helper

class SeedCustodyTests(unittest.TestCase):
    def setUp(self):
        parent = Path(os.environ['USERPROFILE']).resolve() if os.name == 'nt' else None
        self.temp = tempfile.TemporaryDirectory(prefix='copau-seed-synthetic-', dir=parent)
        self.addCleanup(self.temp.cleanup); self.base = Path(self.temp.name).resolve()
        self.public = self.base/'public'; self.public.mkdir()
        self.sid = custody.windows_acl([self.base])[0] if os.name == 'nt' else None
        self.store = seed.PrivateStore(self.base/'private', [self.public], self.sid)
        self.synthetic = b'Q'*32; self.index = 'a'*64

    def generate(self):
        with patch.object(seed.secrets, 'token_bytes', return_value=self.synthetic) as random:
            result = seed.seed_for(self.store, self.index)
            random.assert_called_once_with(32)
        return result

    def test_os_generation_exclusive_seed_and_automatic_reuse(self):
        first, metadata, created = self.generate()
        self.assertTrue(created); self.assertEqual(first, self.synthetic)
        before = self.store.read(seed.SEED)
        with patch.object(seed.secrets, 'token_bytes', side_effect=AssertionError('must reuse')):
            second, again, created = seed.seed_for(self.store, self.index)
        self.assertFalse(created); self.assertEqual((second, again), (first, metadata))
        self.assertEqual(self.store.read(seed.SEED), before)
        with self.assertRaises(custody.Refused):self.store.write(seed.SEED, b'replacement')
        with self.assertRaises(custody.Refused):seed.seed_for(self.store, 'b'*64, reuse=True)
        self.assertEqual(self.store.read(seed.SEED), before)

    def test_permissions_verified_after_writes_and_tampering_refused(self):
        self.generate(); path = self.store.path(seed.SEED)
        self.store.write('bundle.json', b'{}')
        for name in (seed.SEED, 'bundle.json'):self.store.strict(self.store.path(name))
        if os.name == 'nt':
            owner, rows = custody.windows_acl([self.store.root, path, self.store.path('bundle.json')])
            self.assertTrue(all(r['owner'] == owner and r['protected'] for r in rows))
            self.assertTrue(all(rule['allow'] and rule['sid'] == owner for r in rows for rule in r['rules']))
            custody.powershell(r"""
$p=[Console]::In.ReadToEnd() | ConvertFrom-Json
$a=[IO.File]::GetAccessControl($p)
$a.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new(
 [Security.Principal.SecurityIdentifier]::new('S-1-1-0'),'Read','Allow'))
[IO.File]::SetAccessControl($p,$a)
""", str(path))
        else:
            self.assertEqual(stat.S_IMODE(self.store.root.stat().st_mode), 0o700)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            path.chmod(0o640)
        with self.assertRaises(custody.Refused):self.store.read(seed.SEED)
        if os.name == 'nt':custody.powershell(seed.FILE_ACL, str(path))
        else:path.chmod(0o600)
        self.assertEqual(len(self.store.read(seed.SEED)) > 32, True)

    def test_hardlink_and_directory_reparse_or_symlink_refused(self):
        self.generate(); path = self.store.path(seed.SEED); alias = self.base/'alias.json'
        os.link(path, alias)
        try:
            with self.assertRaises(custody.Refused):seed.seed_for(self.store, self.index, reuse=True)
        finally:alias.unlink()
        link = self.base/'linked'
        if os.name == 'nt':
            result = subprocess.run(['cmd.exe','/d','/c','mklink','/J',str(link),str(self.store.root)],
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.assertEqual(result.returncode, 0)
        else:link.symlink_to(self.store.root, target_is_directory=True)
        try:
            other = seed.PrivateStore(link, [self.public], self.sid)
            with self.assertRaises(custody.Refused):seed.seed_for(other, self.index, reuse=True)
        finally:
            if os.name == 'nt':os.rmdir(link)
            else:link.unlink()

    def test_exposed_onedrive_codex_checkout_and_wrong_identity_refused(self):
        for target in (self.public/'key', self.base/'OneDrive Personal/key', self.base/'.codex/key'):
            with self.assertRaises(custody.Refused):
                seed.PrivateStore(target, [self.public], self.sid).initialize()
        checkout = self.base/'checkout'; checkout.mkdir(); (checkout/'.git').write_text('worktree marker')
        with self.assertRaises(custody.Refused):
            seed.PrivateStore(checkout/'key', [self.public], self.sid).initialize()
        if os.name == 'nt':
            with self.assertRaises(custody.Refused):
                seed.PrivateStore(self.base/'other', [self.public], 'S-1-5-21-0-0-0-9999').initialize()

    def test_reuse_requires_existing_seed_and_exact_bundle_without_overwrite(self):
        with self.assertRaises(custody.Refused):seed.seed_for(self.store, self.index, reuse=True)
        self.assertFalse(self.store.root.exists()); original, _, _ = self.generate()
        value = '0123456789abcdef'*2+'01234567'
        raw = custody.encoded(dict(schema='factory-private-expected-values/1', values=[value]))
        provenance = dict(producer={'synthetic': 'b'*64}, output_sha256='c'*64)
        self.store.write('heldout-provenance.json', custody.encoded(provenance))
        self.store.write('copau-expected-values.json', raw)
        before = {p.name:p.read_bytes() for p in self.store.root.iterdir()}
        def producer(root, supplied):
            self.assertEqual(supplied, original); return [value], deepcopy(provenance)
        self.assertEqual(seed.replay(self.store, self.public, original, producer, custody.bundle_info), custody.bundle_info(raw))
        def wrong(root, supplied):return ['x'*40], provenance
        with self.assertRaises(custody.Refused):seed.replay(self.store, self.public, original, wrong, custody.bundle_info)
        self.assertEqual(before, {p.name:p.read_bytes() for p in self.store.root.iterdir()})
        # Exercise the unchanged private-input parser after synthetic admission.
        from lightyear_factory.model_admission import FactoryModelAdmission
        from lightyear_factory.contracts import canonical_hash
        admission = FactoryModelAdmission.__new__(FactoryModelAdmission)
        admission.root = self.public; admission.paths = ('synthetic-plan',)
        plan = dict(private_expected_values=custody.bundle_info(raw))
        admission._committed_json = lambda _: plan
        admission.verify_plan = lambda *a, **k: dict(plan_sha256=canonical_hash(plan, {'content_sha256'}))
        self.assertEqual(admission.private_expected_values(None, self.store.path('copau-expected-values.json')),(value,))

    def test_private_seed_and_values_absent_from_streams_logs_and_errors(self):
        value = 'private-derived-output-'+'Z'*40
        representations = [self.synthetic.decode(), self.synthetic.hex(), base64.b64encode(self.synthetic).decode(), value]
        if os.environ.get('COPAU_OUTPUT_CHILD') != '1':
            result = subprocess.run([sys.executable,'-B','-m','unittest',
                'tests.test_copau_seed_custody.SeedCustodyTests.test_private_seed_and_values_absent_from_streams_logs_and_errors'],
                env=dict(os.environ, COPAU_OUTPUT_CHILD='1'), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            for text in representations:self.assertNotIn(text, result.stdout+result.stderr)
            return
        logfile = self.base/'synthetic.log'; handler = logging.FileHandler(logfile)
        logger = logging.getLogger('copau-synthetic'); logger.addHandler(handler)
        self.addCleanup(handler.close); self.addCleanup(logger.removeHandler, handler)
        def unsafe(args):
            for text in representations:
                print(text); print(text, file=sys.stderr); logging.critical(text); logger.error(text)
                os.write(1, text.encode()); os.write(2, text.encode())
            raise ValueError(value+self.synthetic.hex())
        argv = ['helper','--reviewed-commit','a'*40,'--corpus-index','public.json',
                '--reviewed-corpus-sha256','b'*64,'--exposed-root',str(self.public)]
        out, err = io.StringIO(), io.StringIO()
        with patch.object(sys,'argv',argv), patch.object(helper,'operate',side_effect=unsafe), redirect_stdout(out), redirect_stderr(err):
            self.assertEqual(helper.main(), 1)
        handler.flush(); public = out.getvalue()+err.getvalue()+logfile.read_text()
        for text in representations:self.assertNotIn(text, public)
        self.assertNotIn('Traceback', public); self.assertEqual(logfile.read_text(), '')
        self.assertEqual(out.getvalue(), ''); self.assertIn('REFUSED:', err.getvalue())

if __name__ == '__main__':unittest.main()
