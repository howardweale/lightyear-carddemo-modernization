"""Real age with disposable software identities, synthetic bytes only, CI only."""
from copy import deepcopy
import hashlib
import os
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

from tools import copau_answer_key as helper, copau_seed_custody as seed
from tools import copau_private_prerequisites as custody
from tools.copau_encrypted_store import EncryptedStore, prepare_encrypted
from tests import test_copau_answer_key as fixtures


class EncryptedStoreTests(unittest.TestCase):
    def setUp(self):
        if os.environ.get('GITHUB_ACTIONS') != 'true':
            self.skipTest('CI-only synthetic crypto qualification')
        self.fixture = fixtures.HeldoutCorpusTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.base = self.fixture.base
        self.age = Path(os.environ['SYNTHETIC_AGE'])
        self.pin = os.environ['SYNTHETIC_AGE_SHA256']
        keygen = os.environ['SYNTHETIC_AGE_KEYGEN']
        self.identities = [self.base / ('disposable-' + str(i)) for i in range(3)]
        self.recipients = []
        for identity in self.identities:
            subprocess.run([keygen, '-o', str(identity)], check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.recipients.append(subprocess.check_output([keygen, '-y', str(identity)],
                                  stderr=subprocess.DEVNULL).decode().strip())
        sid = custody.windows_acl([self.base])[0] if os.name == 'nt' else None
        private = seed.PrivateStore(self.base / 'encrypted', [self.base / 'worker'], sid)
        self.store = EncryptedStore(private, self.age, self.pin, self.recipients[:2], self.identities[0])
        self.store.initialize()

    def test_both_recipients_roundtrip_and_no_plaintext_files(self):
        raw = b'{"synthetic":"dummy-answer-012345678901234567890123456789"}'
        self.store.write('expected-source.json', raw)
        self.assertEqual(self.store.read('expected-source.json'), raw)
        self.store.identity = self.identities[1]
        self.assertEqual(self.store.read('expected-source.json'), raw)
        for path in self.store.root.iterdir():
            content = path.read_bytes()
            self.assertTrue(content.startswith(b'age-encryption.org/v1\n'))
            self.assertNotIn(raw, content)
        self.assertFalse((self.store.root / 'expected-source.json').exists())

    def test_wrong_identity_and_tamper_refuse(self):
        self.store.write('expected-source.json', b'{"synthetic":true}')
        self.store.identity = self.identities[2]
        with self.assertRaises(custody.Refused):
            self.store.read('expected-source.json')
        self.store.identity = self.identities[0]
        target = self.store.path('expected-source.json')
        raw = bytearray(target.read_bytes()); raw[-1] ^= 1; target.write_bytes(raw)
        with self.assertRaises(custody.Refused):
            self.store.read('expected-source.json')

    def test_exclusive_names_and_duplicate_recipient_refusal(self):
        self.store.write('expected-source.json', b'one')
        before = self.store.path('expected-source.json').read_bytes()
        with self.assertRaises(custody.Refused):
            self.store.write('expected-source.json', b'two')
        self.assertEqual(before, self.store.path('expected-source.json').read_bytes())
        with self.assertRaises(custody.Refused): self.store.write('../escape.json', b'x')
        with self.assertRaises(custody.Refused):
            EncryptedStore(self.store.inner, self.age, self.pin,
                           [self.recipients[0]] * 2, self.identities[0])

    def test_failed_or_timed_out_encryption_writes_nothing(self):
        for result in (subprocess.CompletedProcess([], 1, b'partial'),
                       subprocess.TimeoutExpired('age', 30)):
            with patch('tools.copau_encrypted_store.subprocess.run',
                       **({'side_effect': result} if isinstance(result, Exception) else {'return_value': result})):
                with self.assertRaises(custody.Refused): self.store.write('expected-source.json', b'x')
            self.assertEqual(list(self.store.root.iterdir()), [])

    def test_seed_reuse_is_encrypted_and_bound_to_index(self):
        value, record, created = seed.seed_for(self.store, 'a' * 64)
        self.assertTrue(created)
        self.assertEqual(seed.seed_for(self.store, 'a' * 64, reuse=True)[:2], (value, record))
        self.assertNotIn(value.hex().encode(), self.store.path(seed.SEED).read_bytes())
        with self.assertRaises(custody.Refused): seed.seed_for(self.store, 'b' * 64, reuse=True)

    def test_original_qualification_uses_encrypted_sink(self):
        provenance = dict(producer='synthetic', input_fields=['synthetic'],
            selected_output_bindings=[dict(selection='existing-judge-computed-record-digest',
                private_identifier_characters=15, length=40)])
        with patch.object(helper, 'run_session', return_value=(self.fixture.values, deepcopy(provenance))), \
             patch.object(helper, 'verify_current_main'):
            report, info = prepare_encrypted(self.store, Path(__file__).resolve().parents[1],
                                            b'Z' * 32, self.fixture.index)
        self.assertTrue(report['qualified'])
        self.assertEqual(info, custody.bundle_info(self.store.read('copau-expected-values.json')))
        for path in self.store.root.iterdir():
            self.assertTrue(path.read_bytes().startswith(b'age-encryption.org/v1\n'))
            self.assertNotIn(self.fixture.values[0].encode(), path.read_bytes())

    def test_no_production_or_changed_tool(self):
        with patch.dict(os.environ, {'GITHUB_ACTIONS': 'false'}):
            with self.assertRaises(custody.Refused):
                EncryptedStore(self.store.inner, self.age, self.pin, self.recipients[:2], self.identities[0])
        with self.assertRaises(custody.Refused):
            EncryptedStore(self.store.inner, self.age, '0' * 64, self.recipients[:2], self.identities[0])
