"""CI-only throwaway byte fixtures; no provider, candidate, signing or spend."""
import base64
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from lightyear_factory.contracts import ContractError
from lightyear_factory.ledger import RunLedger
from lightyear_factory.orchestrator import ArtifactStore


class EncryptedArtifactsTests(unittest.TestCase):
    key = b'0123456789abcdef' * 2  # Public throwaway fixture, never a run key.

    def save(self, store, content=b'fixture prompt and response\x00\xff'):
        return store.write_encrypted('model-transport', 'builder', content,
                                     key=self.key, key_id='fixture-key-v1')

    def envelope(self, root, ref):
        return json.loads((root / ref['path']).read_bytes())

    def decrypt(self, envelope, key=None):
        aad = json.dumps(envelope['context'], sort_keys=True, separators=(',', ':')).encode()
        return AESGCM(key or self.key).decrypt(
            base64.b64decode(envelope['nonce_base64']),
            base64.b64decode(envelope['ciphertext_base64']), aad)

    def test_exact_bytes_encrypted_in_same_run_lifecycle_and_hash_chained_reference(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); store = ArtifactStore(root / 'artifacts', 'fixture-run')
            content = b'full fixture prompt, raw response and tool call\x00\xff'
            first = store.write('plan', 'planner', 'public', {'fixture': True})
            ref = self.save(store, content); envelope = self.envelope(root, ref)
            raw = (root / ref['path']).read_bytes()
            self.assertEqual(2, ref['sequence'])
            self.assertEqual(content, self.decrypt(envelope))
            self.assertNotIn(content, raw)
            self.assertNotIn(b'full fixture prompt', raw)
            self.assertNotIn(self.key, raw)
            self.assertEqual(sha256(content).hexdigest(), ref['plaintext_sha256'])
            self.assertEqual(sha256(raw).hexdigest(), ref['artifact_sha256'])
            self.assertEqual(sha256(base64.b64decode(envelope['ciphertext_base64'])).hexdigest(),
                             ref['ciphertext_sha256'])
            ledger = RunLedger(root / 'events.jsonl')
            ledger.append('RUNNING', 'model-record-retained', ref)
            self.assertTrue(ledger.verify())
            self.assertNotIn(content, ledger.path.read_bytes())
            self.assertEqual({'plan', 'model-transport'}, {first['artifact_type'], ref['artifact_type']})

    def test_wrong_key_and_tampered_context_or_ciphertext_are_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); store = ArtifactStore(root / 'artifacts', 'fixture-run')
            ref = self.save(store); original = self.envelope(root, ref)
            with self.assertRaises(InvalidTag):
                self.decrypt(original, b'x' * 32)
            for field, value in [('run_id', 'other-run'), ('role', 'analyst'),
                                 ('sequence', 99), ('key_id', 'other-key'),
                                 ('plaintext_sha256', '0' * 64)]:
                changed = json.loads(json.dumps(original)); changed['context'][field] = value
                with self.subTest(field=field), self.assertRaises(InvalidTag):
                    self.decrypt(changed)
            changed = json.loads(json.dumps(original))
            data = bytearray(base64.b64decode(changed['ciphertext_base64'])); data[0] ^= 1
            changed['ciphertext_base64'] = base64.b64encode(data).decode()
            with self.assertRaises(InvalidTag): self.decrypt(changed)

    def test_duplicate_plaintext_has_distinct_encryption_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); store = ArtifactStore(root / 'artifacts', 'fixture-run')
            first = self.save(store); second = self.save(store)
            self.assertEqual(first['plaintext_sha256'], second['plaintext_sha256'])
            self.assertNotEqual(first['ciphertext_sha256'], second['ciphertext_sha256'])
            self.assertNotEqual(self.envelope(root, first)['nonce_base64'],
                                self.envelope(root, second)['nonce_base64'])
            before = (root / first['path']).read_bytes()
            with self.assertRaises(FileExistsError):
                self.save(ArtifactStore(root / 'artifacts', 'fixture-run'))
            self.assertEqual(before, (root / first['path']).read_bytes())

    def test_invalid_input_and_durability_failure_cannot_return_a_public_reference(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); store = ArtifactStore(root / 'artifacts', 'fixture-run')
            for changes in [{'artifact_type': '../escape'}, {'role': 'builder/escape'},
                            {'content': 'not bytes'}, {'key': b'short'}, {'key_id': '../key'}]:
                args = dict(artifact_type='model-transport', role='builder', content=b'fixture',
                            key=self.key, key_id='fixture-key-v1'); args.update(changes)
                with self.subTest(changes=changes), self.assertRaises(ContractError):
                    store.write_encrypted(**args)
            self.assertFalse(store.root.exists())
            with patch('os.fsync', side_effect=OSError('fixture durability failure')):
                with self.assertRaises(OSError): self.save(store)
            # Failed persistence never creates a ledger reference or plaintext fallback.
            self.assertFalse((root / 'events.jsonl').exists())
            for path in store.root.iterdir():
                self.assertNotIn(b'fixture prompt and response', path.read_bytes())
