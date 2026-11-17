"""Synthetic public-only tests. No reference/compiler/Docker/freeze dispatch."""
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

from tools import intcalc_public_freeze_wrapper as w


class PublicFreezeWrapperTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.commit, self.tree = 'a' * 40, 'b' * 40

    def row(self):
        return dict(schema='reference-two-source-public-freeze-approval/1', authority='Howard',
                    authorize_public_freeze=True, scope='PC-01..PC-16 only; no hidden set',
                    wrapper_commit=self.commit, wrapper_tree=self.tree,
                    qualification_commit=w.QUALIFICATION_COMMIT, qualification_tree=w.QUALIFICATION_TREE,
                    qualification_sha256=w.QUALIFICATION_SHA, evidence_manifest_sha256=w.EVIDENCE_MANIFEST_SHA,
                    binding_sha256=w.BINDING_SHA, public_suite_sha256=w.SUITE_SHA)

    def test_exact_approval_requires_both_source_identities(self):
        raw = w.canonical(self.row())
        self.assertEqual(w.approval(raw, w.sha(raw), self.commit, self.tree), self.row())
        for key in ('wrapper_commit', 'wrapper_tree', 'qualification_commit', 'qualification_tree',
                    'qualification_sha256', 'public_suite_sha256', 'binding_sha256'):
            with self.subTest(key=key):
                row = self.row(); row[key] = '0' * len(row[key]); altered = w.canonical(row)
                with self.assertRaisesRegex(w.Refused, '^freeze-approval$'):
                    w.approval(altered, w.sha(altered), self.commit, self.tree)

    def test_adoption_is_not_public_freeze_authority(self):
        for value in (False, None, 1):
            row = self.row(); row['authorize_public_freeze'] = value; raw = w.canonical(row)
            with self.subTest(value=value), self.assertRaisesRegex(w.Refused, '^freeze-approval$'):
                w.approval(raw, w.sha(raw), self.commit, self.tree)

    def test_approval_is_closed_and_exact_bytes_hashed(self):
        raw = w.canonical(self.row())
        with self.assertRaisesRegex(w.Refused, '^freeze-approval$'):
            w.approval(raw + b'\n', w.sha(raw), self.commit, self.tree)
        row = self.row(); row['extra'] = True; raw = w.canonical(row)
        with self.assertRaisesRegex(w.Refused, '^freeze-approval$'):
            w.approval(raw, w.sha(raw), self.commit, self.tree)

    def test_strict_json_duplicates_floats_and_nonfinite_refused(self):
        for raw in (b'{"x":1,"x":2}', b'{"x":1.0}', b'{"x":NaN}', b'{"x":Infinity}'):
            with self.subTest(raw=raw), self.assertRaises(w.Refused):
                w.strict(raw)

    def test_actual_ci_head_not_qualification_head(self):
        env = dict(GITHUB_ACTIONS='true', GITHUB_EVENT_NAME='workflow_dispatch',
                   GITHUB_REF='refs/heads/main', GITHUB_REPOSITORY=w.REPOSITORY,
                   GITHUB_SHA=self.commit, GITHUB_RUN_ID='123', GITHUB_RUN_ATTEMPT='1')
        w.ci_identity(env, self.commit)
        for key, bad in (('GITHUB_SHA', w.QUALIFICATION_COMMIT), ('GITHUB_EVENT_NAME', 'pull_request'),
                         ('GITHUB_REF', 'refs/heads/other'), ('GITHUB_REPOSITORY', 'x/y'),
                         ('GITHUB_RUN_ID', 'no'), ('GITHUB_RUN_ATTEMPT', '')):
            with self.subTest(key=key), self.assertRaisesRegex(w.Refused, '^freeze-ci$'):
                w.ci_identity(dict(env, **{key: bad}), self.commit)

    @staticmethod
    def archive(rows):
        output = io.BytesIO()
        with zipfile.ZipFile(output, 'w') as archive:
            for name, data in rows:
                archive.writestr(name, data)
        return output.getvalue()

    def test_safe_archive_and_zero_byte_member(self):
        dest = self.root / 'evidence'
        w.unpack(self.archive([('public/PC-01/observations/reference/stdout', b'OK\n'),
                               ('controller.log', b'')]), dest)
        self.assertEqual((dest / 'public/PC-01/observations/reference/stdout').read_bytes(), b'OK\n')
        self.assertEqual((dest / 'controller.log').read_bytes(), b'')

    def test_archive_paths_refused_before_writes(self):
        for i, name in enumerate(('../escape', '/absolute', 'C:/escape', 'a\\b', 'a//b', 'a/./b', 'folder/')):
            dest = self.root / str(i)
            with self.subTest(name=name), self.assertRaises(w.Refused):
                w.unpack(self.archive([(name, b'x')]), dest)
            self.assertFalse(dest.exists())

    def test_duplicate_archive_refused(self):
        with self.assertWarns(UserWarning):
            raw = self.archive([('same', b'a'), ('same', b'b')])
        with self.assertRaisesRegex(w.Refused, '^freeze-archive$'):
            w.unpack(raw, self.root / 'duplicate')

    def test_archive_symlink_refused(self):
        output = io.BytesIO()
        with zipfile.ZipFile(output, 'w') as archive:
            info = zipfile.ZipInfo('link'); info.create_system = 3; info.external_attr = 0o120777 << 16
            archive.writestr(info, 'other')
        with self.assertRaisesRegex(w.Refused, '^freeze-archive$'):
            w.unpack(output.getvalue(), self.root / 'link')

    def test_archive_limit_refused(self):
        raw = self.archive([('one', b'12'), ('two', b'34')])
        with patch.object(w, 'MAX_BYTES', 3), self.assertRaisesRegex(w.Refused, '^freeze-archive$'):
            w.unpack(raw, self.root / 'large')

    def test_destination_is_fresh(self):
        dest = self.root / 'existing'; dest.mkdir()
        with self.assertRaisesRegex(w.Refused, '^freeze-path$'):
            w.unpack(self.archive([('a', b'a')]), dest)

    def test_exclusive_and_readback(self):
        path = self.root / 'receipt.json'
        w.exclusive(path, b'{}\n')
        with self.assertRaisesRegex(w.Refused, '^freeze-write$'):
            w.exclusive(path, b'new')
        self.assertEqual(path.read_bytes(), b'{}\n')

    def test_readback_mismatch_refuses(self):
        with patch.object(w, 'checked_file', return_value=b'wrong'), self.assertRaisesRegex(w.Refused, '^freeze-readback$'):
            w.exclusive(self.root / 'mismatch', b'right')

    def test_git_dirty_refuses(self):
        outputs = [self.commit, self.tree, ' M tools/example.py']
        def run(*args, **kwargs):
            return SimpleNamespace(returncode=0, stdout=(outputs.pop(0) + '\n').encode(), stderr=b'')
        with patch.object(w.subprocess, 'run', side_effect=run), self.assertRaisesRegex(w.Refused, '^freeze-source-dirty$'):
            w.git_identity(self.root)

    def fixture(self):
        cases = []
        for n in range(1, 17):
            case = dict(id='PC-%02d' % n, hand_outputs=dict(stdout={'path': 'stdout'}), hand_exit=12 if n in (10, 11, 12) else 0)
            cases.append(case)
            path = self.root / 'public' / case['id'] / 'observations/reference/stdout'
            path.parent.mkdir(parents=True); path.write_bytes(b'public synthetic\n')
        ref = SimpleNamespace(ROOT=self.root, joined=lambda root, desc: b'public synthetic\n',
                              comparison_policy=lambda case: case['hand_exit'] == 0)
        return SimpleNamespace(ref=ref), {'suite': {'path': 'suite/SUITE.json'}}, {'cases': cases}

    def test_public_outputs_preserve_abend_file_policy(self):
        q, req, suite = self.fixture()
        rows = dict(w.public_outputs(q, self.root, req, suite))
        self.assertEqual(len(rows), 32)
        for n in range(1, 17):
            case = json.loads(rows['PC-%02d/expected.json' % n])
            self.assertEqual(case['compare_output_files'], n not in (10, 11, 12))
            self.assertEqual(set(case['outputs']), {'stdout'})
            self.assertEqual(rows['PC-%02d/stdout' % n], b'public synthetic\n')

    def test_reference_hand_mismatch_blocks_outputs(self):
        q, req, suite = self.fixture()
        q.ref.joined = lambda root, desc: b'different'
        with self.assertRaisesRegex(w.Refused, '^freeze-reference-hand$'):
            w.public_outputs(q, self.root, req, suite)

    def test_missing_case_refuses(self):
        q, req, suite = self.fixture(); suite['cases'].pop()
        with self.assertRaisesRegex(w.Refused, '^freeze-criterion$'):
            w.public_outputs(q, self.root, req, suite)

    def test_manifest_records_both_sources_and_approval_without_relabeling(self):
        files = [dict(path='PC-01/stdout', bytes=1, sha256='1' * 64)]
        manifest = w.answer_manifest((self.commit, self.tree), {'named_limits': ['limit']},
                                     files, '2' * 64, '3' * 64, '4' * 64,
                                     {'GITHUB_RUN_ID': '123', 'GITHUB_RUN_ATTEMPT': '1'})
        self.assertEqual(manifest['qualification_commit'], w.QUALIFICATION_COMMIT)
        self.assertEqual(manifest['qualification_tree'], w.QUALIFICATION_TREE)
        self.assertEqual(manifest['wrapper_commit'], self.commit)
        self.assertEqual(manifest['wrapper_tree'], self.tree)
        self.assertEqual(manifest['approval_sha256'], '2' * 64)
        self.assertEqual(manifest['files'], files)
        self.assertEqual(manifest['schema'], 'reference-public-answer-key/2')
        self.assertNotIn('qualified', manifest)

    def test_fresh_output_refuses_traversal_or_checkout_destination(self):
        wrapper = self.root / 'wrapper'; wrapper.mkdir()
        source = self.root / 'source'; source.mkdir()
        for path in (self.root / 'unused' / '..' / 'output', wrapper / 'output', source / 'output', Path('relative')):
            with self.subTest(path=str(path)), self.assertRaisesRegex(w.Refused, '^freeze-path$'):
                w.fresh_output(path, wrapper, source)
        self.assertEqual(w.fresh_output(self.root / 'output', wrapper, source), self.root / 'output')

    def test_fetch_is_fixed_public_asset_surface(self):
        with self.assertRaisesRegex(w.Refused, '^freeze-fetch$'):
            w.fetch_asset('arbitrary-secret', '0' * 64, 100)


if __name__ == '__main__':
    unittest.main()
