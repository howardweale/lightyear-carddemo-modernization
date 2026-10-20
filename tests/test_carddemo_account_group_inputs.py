"""CI-only refusal fixtures for composed descriptor input closure."""
from copy import deepcopy
from unittest import TestCase
from tools.carddemo_account_evidence import BoundEvidence
from tools.carddemo_account_group import _input_closure
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import json


class AccountGroupInputsTest(TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.desc = {'inventory': self.put('inventory.json', b'{}'),
                     'run': self.put('run.json', b'{}'),
                     'archives': {'example.zip': self.put('archive.zip', b'archive')},
                     'source_bindings': {'source.java': self.put('source.java', b'class Example {}')}}
        self.members = {value['path']: value['sha256'] for value in
                        [self.desc['inventory'], self.desc['run'],
                         *self.desc['archives'].values(), *self.desc['source_bindings'].values()]}

    def put(self, path, raw):
        (self.root / path).write_bytes(raw)
        return {'path': path, 'sha256': sha256(raw).hexdigest()}

    def evidence(self):
        self.desc['manifest'] = self.put('manifest.json', json.dumps(self.members).encode())
        return BoundEvidence(self.root, self.desc['manifest'])

    def test_complete_inputs_leave_captured_bytes_unchanged(self):
        evidence = self.evidence(); before = deepcopy(self.desc)
        _input_closure(self.desc, evidence, 'descriptor.json')
        self.assertEqual(self.desc, before)
        self.assertEqual(evidence.read(self.desc['run']), b'{}')

    def test_unreferenced_manifest_member_is_refused(self):
        extra = self.put('unreferenced.txt', b'extra')
        self.members[extra['path']] = extra['sha256']
        with self.assertRaisesRegex(ValueError, 'input-closure'):
            _input_closure(self.desc, self.evidence(), 'descriptor.json')

    def test_duplicate_role_and_descriptor_alias_are_refused(self):
        evidence = self.evidence()
        with self.assertRaisesRegex(ValueError, 'input-alias'):
            _input_closure(self.desc, evidence, 'RUN.JSON')
        self.desc['run'] = self.desc['inventory']
        with self.assertRaisesRegex(ValueError, 'input-alias'):
            _input_closure(self.desc, evidence, 'descriptor.json')

    def test_manifest_descriptor_alias_is_refused(self):
        with self.assertRaisesRegex(ValueError, 'input-alias'):
            _input_closure(self.desc, self.evidence(), 'MANIFEST.JSON')

    def test_unbound_digest_and_malformed_roles_are_refused(self):
        evidence = self.evidence()
        self.desc['run']['sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'unbound-reference'):
            _input_closure(self.desc, evidence, 'descriptor.json')
        self.desc['archives'] = []
        with self.assertRaisesRegex(ValueError, 'input-bindings'):
            _input_closure(self.desc, evidence, 'descriptor.json')
