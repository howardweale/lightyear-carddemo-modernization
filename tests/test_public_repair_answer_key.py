"""CI-only synthetic manifest-v2 fixtures. These do not perform a public freeze."""
from dataclasses import replace
import json
from pathlib import Path
import shutil
import stat
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from lightyear_factory import public_repair_answer_key as key


REPO = Path(__file__).resolve().parents[1]
PUBLIC = REPO / 'tests/fixtures/reference-execution/public-cases'


class PublishedBindingTests(unittest.TestCase):
    def test_bound_release_refuses_a_resealed_binding(self):
        binding = (REPO / 'spec/public-answer-key-loader/2026-11-18-r1/RELEASE-BINDING.json').read_bytes()
        self.assertEqual(key.sha(binding), key.RELEASE_BINDING_SHA256)
        with self.assertRaisesRegex(key.Refused, '^answer-release-binding$'):
            key.published_key(binding + b' ', 'anything', b'')

    def test_bound_release_refuses_changed_tag_and_archive(self):
        binding = (REPO / 'spec/public-answer-key-loader/2026-11-18-r1/RELEASE-BINDING.json').read_bytes()
        entry = key.strict(binding)
        with self.assertRaisesRegex(key.Refused, '^answer-release-tag$'):
            key.published_key(binding, entry['release_tag'] + '-other', b'')
        for archive in (b'', bytes(entry['zip_bytes'])):
            with self.assertRaisesRegex(key.Refused, '^answer-release-archive$'):
                key.published_key(binding, entry['release_tag'], archive)


class AnswerKeyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.answer = self.root / 'frozen'
        self.inputs = self.root / 'public-inputs'
        self.answer.mkdir()
        self.inputs.mkdir()
        suite_raw = (PUBLIC / 'SUITE.json').read_bytes()
        self.assertEqual(key.sha(suite_raw), key.adapter.PUBLIC_SUITE)
        (self.inputs / 'SUITE.json').write_bytes(suite_raw)
        self.suite = json.loads(suite_raw)
        self.review = key.ReviewedKey('0' * 64, '1' * 40, '2' * 40, '3' * 64, 123, 1)
        approval = key.canonical(key.approval_expected(self.review)) + b'\n'
        (self.answer / 'APPROVAL.json').write_bytes(approval)
        self.review = replace(self.review, approval_sha256=key.sha(approval))
        files = []
        for c in self.suite['cases']:
            folder = self.answer / c['id']
            folder.mkdir()
            outputs = {}
            for channel, descriptor in c['hand_outputs'].items():
                # Test fixture construction only: public hand bytes stand in for the
                # future reference bytes. No qualification or freeze claim is made.
                raw = (PUBLIC / descriptor['path']).read_bytes()
                self.assertEqual(key.sha(raw), descriptor['sha256'])
                (folder / channel).write_bytes(raw)
                row = dict(path=c['id'] + '/' + channel, sha256=key.sha(raw), bytes=len(raw))
                outputs[channel] = row
                files.append(row)
            expected = key.canonical(dict(exit=c['hand_exit'],
                compare_output_files=c['compare_output_files'], outputs=outputs)) + b'\n'
            (folder / 'expected.json').write_bytes(expected)
            files.append(dict(path=c['id'] + '/expected.json', sha256=key.sha(expected), bytes=len(expected)))
            for descriptor in c['inputs'].values():
                p = self.inputs / descriptor['path']
                p.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(PUBLIC / descriptor['path'], p)
        self.manifest = dict(key.QUALIFICATION, schema='reference-public-answer-key/2',
            visibility='public', wrapper_commit=self.review.wrapper_commit,
            wrapper_tree=self.review.wrapper_tree, wrapper_tool_sha256='4' * 64,
            wrapper_workflow_sha256='5' * 64, approval_sha256=self.review.approval_sha256,
            run_id=123, run_attempt=1, named_limits=['synthetic only', 'not frozen', 'not qualified'], files=files)
        self.reseal()

    def reseal(self):
        raw = key.canonical(self.manifest) + b'\n'
        (self.answer / 'MANIFEST.json').write_bytes(raw)
        self.review = replace(self.review, manifest_sha256=key.sha(raw))

    def load(self):
        return key.load(self.answer, self.inputs, self.review)

    def rewrite_case(self, case_id, change):
        p = self.answer / case_id / 'expected.json'
        row = json.loads(p.read_bytes())
        change(row)
        raw = key.canonical(row) + b'\n'
        p.write_bytes(raw)
        item = next(x for x in self.manifest['files'] if x['path'] == case_id + '/expected.json')
        item.update(bytes=len(raw), sha256=key.sha(raw))
        self.reseal()

    def test_all_cases_without_any_hand_output_path(self):
        cases, provenance = self.load()
        self.assertEqual(len(cases), 16)
        self.assertFalse(any(self.inputs.rglob('hand')))
        self.assertEqual(provenance['qualification_commit'], key.QUALIFICATION['qualification_commit'])
        self.assertEqual(provenance['wrapper_commit'], self.review.wrapper_commit)
        self.assertEqual(provenance['manifest_sha256'], self.review.manifest_sha256)
        for case in cases[9:12]:
            self.assertFalse(case['compare_output_files'])
            self.assertEqual(set(case['expected']), {'stdout', 'stderr', 'exit'})
            self.assertEqual(case['expected']['exit'], 12)

    def test_missing_review_never_falls_back(self):
        with self.assertRaisesRegex(key.Refused, '^answer-review-binding$'):
            key.load(self.answer, self.inputs, None)

    def test_manifest_byte_hash_includes_newline(self):
        p = self.answer / 'MANIFEST.json'
        p.write_bytes(p.read_bytes().rstrip(b'\n'))
        with self.assertRaisesRegex(key.Refused, '^answer-manifest-hash$'):
            self.load()

    def test_each_provenance_pin_is_enforced(self):
        for field in key.QUALIFICATION:
            with self.subTest(field=field):
                old = self.manifest[field]
                self.manifest[field] = '0' * len(old)
                self.reseal()
                with self.assertRaisesRegex(key.Refused, '^answer-provenance$'):
                    self.load()
                self.manifest[field] = old
                self.reseal()

    def test_review_join_and_boolean_run_id(self):
        for field, value in [('wrapper_tree', '6' * 40), ('run_id', True)]:
            with self.subTest(field=field):
                old = self.manifest[field]
                self.manifest[field] = value
                self.reseal()
                with self.assertRaisesRegex(key.Refused, '^answer-review-binding$'):
                    self.load()
                self.manifest[field] = old
                self.reseal()

    def test_approval_bytes_and_scope(self):
        p = self.answer / 'APPROVAL.json'
        row = json.loads(p.read_bytes())
        row['authorize_public_freeze'] = False
        p.write_bytes(key.canonical(row))
        with self.assertRaisesRegex(key.Refused, '^answer-approval-hash$'):
            self.load()
        self.review = replace(self.review, approval_sha256=key.sha(p.read_bytes()))
        self.manifest['approval_sha256'] = self.review.approval_sha256
        self.reseal()
        with self.assertRaisesRegex(key.Refused, '^answer-approval$'):
            self.load()

    def test_duplicate_json_and_noninteger_numbers(self):
        for raw in (b'{"x":1,"x":2}', b'{"x":0.1}', b'{"x":NaN}', b'{"x":Infinity}', b'\xff'):
            with self.subTest(raw=raw), self.assertRaisesRegex(key.Refused, '^answer-json$'):
                key.strict(raw)

    def test_unexpected_manifest_key(self):
        self.manifest['fallback'] = 'hand'
        self.reseal()
        with self.assertRaisesRegex(key.Refused, '^answer-manifest-shape$'):
            self.load()

    def test_duplicate_or_missing_inventory_rows(self):
        original = list(self.manifest['files'])
        self.manifest['files'][-1] = self.manifest['files'][0]
        self.reseal()
        with self.assertRaisesRegex(key.Refused, '^answer-descriptor$'):
            self.load()
        self.manifest['files'] = original[:-1]
        self.reseal()
        with self.assertRaisesRegex(key.Refused, '^answer-files$'):
            self.load()

    def test_exact_inventory_excludes_unlisted_files(self):
        for p in (self.answer / 'extra', self.answer / 'PC-01' / 'extra'):
            with self.subTest(path=p.name):
                p.write_bytes(b'public extra')
                with self.assertRaisesRegex(key.Refused, '^answer-inventory$'):
                    self.load()
                p.unlink()

    def test_frozen_bytes_must_match_both_hashes(self):
        p = self.answer / 'PC-01/stdout'
        raw = p.read_bytes() + b'x'
        p.write_bytes(raw)
        with self.assertRaisesRegex(key.Refused, '^answer-file-hash$'):
            self.load()
        item = next(x for x in self.manifest['files'] if x['path'] == 'PC-01/stdout')
        item.update(bytes=len(raw), sha256=key.sha(raw))
        self.rewrite_case('PC-01', lambda c: c['outputs']['stdout'].update(item))
        with self.assertRaisesRegex(key.Refused, '^answer-reference-hand-join$'):
            self.load()

    def test_abend_comparison_policy_cannot_expand(self):
        self.rewrite_case('PC-10', lambda c: c.update(compare_output_files=True))
        with self.assertRaisesRegex(key.Refused, '^answer-case-policy$'):
            self.load()

    def test_boolean_exit_is_not_an_integer_exit(self):
        self.rewrite_case('PC-01', lambda c: c.update(exit=False))
        with self.assertRaisesRegex(key.Refused, '^answer-case-policy$'):
            self.load()

    def test_descriptor_cannot_cross_case_boundary(self):
        self.rewrite_case('PC-01', lambda c: c['outputs']['stdout'].update(path='PC-02/stdout'))
        with self.assertRaisesRegex(key.Refused, '^answer-reference-hand-join$'):
            self.load()

    def test_input_and_suite_hashes(self):
        p = self.inputs / 'PC-01/input/ACCTFILE.bin'
        p.write_bytes(p.read_bytes() + b'x')
        with self.assertRaisesRegex(key.Refused, '^answer-input-hash$'):
            self.load()
        (self.inputs / 'SUITE.json').write_bytes(b'{}')
        with self.assertRaisesRegex(key.Refused, '^answer-suite-hash$'):
            self.load()

    def test_path_spelling_and_special_files(self):
        for name in ('../x', 'a\\b', '/x', 'a//b', 'a/./b', 'C:x', 'a\x00b'):
            with self.subTest(name=name), self.assertRaisesRegex(key.Refused, '^answer-path$'):
                key.relative(name)
        with self.assertRaisesRegex(key.Refused, '^answer-path$'):
            key.regular(SimpleNamespace(st_mode=stat.S_IFLNK, st_file_attributes=0))
        with self.assertRaisesRegex(key.Refused, '^answer-reparse$'):
            key.regular(SimpleNamespace(st_mode=stat.S_IFREG, st_file_attributes=0x400))

    def test_file_and_total_bounds(self):
        self.manifest['files'][0]['bytes'] = key.FILE_BYTES + 1
        self.reseal()
        with self.assertRaisesRegex(key.Refused, '^answer-descriptor$'):
            self.load()
        self.manifest['files'][0]['bytes'] -= 1
        self.reseal()
        with patch.object(key, 'TOTAL_BYTES', 0):
            with self.assertRaisesRegex(key.Refused, '^answer-total-size$'):
                self.load()

    def test_loader_never_calls_worker_or_hand_loader(self):
        worker = SimpleNamespace()
        records = []
        def retain(raw):
            records.append(raw)
            return key.sha(raw)
        with patch.object(key.adapter, 'public_suite', side_effect=AssertionError('hand fallback')):
            port = key.FrozenPublicAdapter(worker, self.answer, self.inputs, REPO,
                                           self.review, retain, clock=lambda: 1)
        inner = key.canonical({'schema': 'public-evaluation-receipt/1'})
        self.assertEqual(port.retain(inner), key.sha(inner))
        outer = json.loads(records[-1])
        self.assertEqual(len(records), 2)
        self.assertEqual(outer['evaluation_sha256'], key.sha(records[0]))
        self.assertEqual(outer['answer_key']['manifest_sha256'], self.review.manifest_sha256)

    def test_evaluation_records_frozen_binding_and_keeps_answers_out_of_worker(self):
        cases, _ = self.load()
        records = []
        built = dict(status='BUILT', artifact_sha256='a' * 64, build_receipt_sha256='b' * 64)
        class Worker:
            index = 0
            def run_public(inner, build, inputs, timestamp, date, deadline, limits):
                case = cases[inner.index]
                inner.index += 1
                self.assertEqual(set(inputs), key.INPUT_NAMES)
                self.assertNotIn('expected', inputs)
                values = dict(ACCTFILE=b'', TRANSACT=b'', stdout=b'', stderr=b'', exit=0)
                values.update(case['expected'])
                return dict(values, cleanup=True, receipt_sha256='c' * 64,
                    artifact_sha256=build['artifact_sha256'], build_receipt_sha256=build['build_receipt_sha256'],
                    timed_out=False, output_capped=False)
        def retain(raw):
            records.append(raw)
            return key.sha(raw)
        port = key.FrozenPublicAdapter(Worker(), self.answer, self.inputs, REPO,
                                       self.review, retain, clock=lambda: 1)
        result = port.evaluate_public(built, key.adapter.PUBLIC_SUITE, 601)
        self.assertEqual((result['match'], result['different'], result['total']), (16, 0, 16))
        self.assertEqual(result['receipt_sha256'], key.sha(records[-1]))
        self.assertEqual(json.loads(records[-1])['answer_key']['wrapper_tree'], self.review.wrapper_tree)

    def test_bad_retention_readback_refuses(self):
        port = key.FrozenPublicAdapter(None, self.answer, self.inputs, REPO,
                                       self.review, lambda raw: '0' * 64)
        with self.assertRaisesRegex(key.Refused, '^answer-receipt-readback$'):
            port.retain(b'{}')


if __name__ == '__main__':
    unittest.main()
