"""CI-only full retained-proof integration and refusal tests."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest
from tools.carddemo_account_archive import verify_archives
from tools.carddemo_account_evidence import BoundEvidence, json_document
from tools.carddemo_account_git import verify_git_sources
from tools.carddemo_account_group import SCOPES, COBOL
from tools.carddemo_account_observations import verify_observations
from tools import carddemo_account_status as status

ROOT = Path(__file__).resolve().parents[1]


class AccountPublicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.record = status.load(ROOT)
        ref = json_document((ROOT/status.INDEX).read_bytes())
        cls.desc = json_document((ROOT/ref['path']).read_bytes())
        cls.evidence = BoundEvidence(ROOT, cls.desc['manifest'])
        cls.archives = verify_archives(cls.evidence, cls.evidence.document(cls.desc['inventory']), cls.desc['archives'])
        cls.scopes = {k: cls.evidence.document(cls.desc['source_bindings'][p]) for k, p in SCOPES.items()}
        cls.source = cls.scopes['account_input_java']['source']

    def test_complete_bound_current_measurement(self):
        row = self.record
        self.assertEqual((row['mutation']['killed'], row['mutation']['total']), (882, 950))
        self.assertEqual(row['hash_closure'], {'source_and_mapping_hashes': 156, 'artifact_hashes': 176})
        self.assertEqual(row['validation_paragraph_count'], 12)
        self.assertEqual(row['classes']['AccountLocationRules']['killed'], 2)
        self.assertEqual(row['observations']['retained_rows_verified'], dict(api=678, browser=678, mutation=678))
        self.assertEqual(row['measurement_date'], '2026-10-19')
        self.assertEqual(row['original_receipt_date'], '2026-10-18')
        self.assertFalse(row['whole_screen_idiomatic'])
        self.assertFalse(row['merge_approved'])

    def test_old_base_is_disclosed_and_cannot_be_relabelled_main(self):
        desc = self.desc
        self.assertEqual(self.record['tested_parents'][0], desc['base_head'])
        with self.assertRaisesRegex(ValueError, 'tested-tree-parents'):
            verify_git_sources(desc['git_objects'], self.evidence, desc['source_head'], desc['tested_commit'],
                               '364bb10bed259d6602fdcd476d43f6f9a194539a', desc['source_bindings'])

    def test_git_object_kind_or_bytes_cannot_be_substituted(self):
        desc = self.desc; refs = dict(desc['git_objects'])
        refs[desc['source_head']] = refs[desc['tested_commit']]
        with self.assertRaisesRegex(ValueError, 'object-hash'):
            verify_git_sources(refs, self.evidence, desc['source_head'], desc['tested_commit'], desc['base_head'], desc['source_bindings'])

    def test_changed_retained_screen_database_or_order_refused(self):
        for kind in ('screen', 'database', 'order'):
            archives = {name: dict(files) for name, files in self.archives.items()}
            files = archives['carddemo-proof-browser']; frames = json.loads(files['browser/frames.json'])
            if kind == 'screen': frames[0]['screen']['program'] = 'WRONG'
            elif kind == 'database': frames[0]['database_after']['path'] = '0'*64 + '.json'
            else: frames[0], frames[1] = frames[1], frames[0]
            files['browser/frames.json'] = json.dumps(frames).encode()
            with self.subTest(kind=kind), self.assertRaises((ValueError, KeyError)):
                verify_observations(archives, self.scopes, self.source)

    def test_trace_scope_cannot_add_a_paragraph(self):
        scopes = deepcopy(self.scopes)
        scopes['account_location_java']['validation_paragraphs'].append('9999-UNPROVED')
        with self.assertRaisesRegex(ValueError, 'trace-scope'):
            verify_observations(self.archives, scopes, self.source)

    def test_bound_text_helpers_are_preserved_and_unknown_methods_refused(self):
        methods = self.record['observations']['trace_links']['account_text_money_java']['methods']
        self.assertTrue({'empty', 'text'} <= {row['method'] for row in methods})
        archives = {name: dict(files) for name, files in self.archives.items()}
        for files in archives.values():
            for path in list(files):
                if path.endswith('/account-text-money-trace.json'):
                    trace = json.loads(files[path]); trace['methods'][0]['method'] = 'unproved'
                    files[path] = json.dumps(trace).encode()
        with self.assertRaisesRegex(ValueError, 'trace-scope'):
            verify_observations(archives, self.scopes, self.source)

    def test_ci_outputs_are_deterministic_and_never_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            status.publish_ci(folder, ROOT)
            for path, raw in status.outputs(self.record).items(): self.assertEqual((Path(folder)/path).read_bytes(), raw)
            target = Path(folder)/next(iter(status.outputs(self.record)))
            target.write_bytes(b'preserved historical bytes')
            with self.assertRaisesRegex(ValueError, 'overwrite'): status.publish_ci(folder, ROOT)
            self.assertEqual(target.read_bytes(), b'preserved historical bytes')
