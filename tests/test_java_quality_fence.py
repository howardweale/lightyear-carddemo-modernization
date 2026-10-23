"""Synthetic CI-only fence tests; no factory, private data or model execution."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from tools import check_java_quality_fence as fence


class JavaQualityFenceTests(unittest.TestCase):
    def fixture(self):
        documents = {}

        def put(path, value):
            raw = json.dumps(value, sort_keys=True).encode()
            documents[path] = raw
            return dict(path=path, sha256=hashlib.sha256(raw).hexdigest())

        frozen = 'factory/carddemo-web/service/src/test/java/ExampleTest.java'
        original = put(fence.ORIGINAL, dict(files=[dict(path=frozen, sha256='1' * 64)]))
        put(fence.AMENDMENT, dict(original_manifest_sha256=original['sha256'],
            files=[dict(path='factory/carddemo-web/service/pom.xml', sha256='2' * 64)],
            existing_authorized_change=dict(path='original-judge.py', sha256='3' * 64)))
        scope = put('scope.json', dict(candidate_directory='service/authorization',
            interfaces=dict(source_path='service/TransactionService.java')))
        workspace = put('workspace.json', {'worker/input.txt': '4' * 64})
        put(fence.F2, dict(schema='copau-f2-preparation/1',
            engineering_source_bindings=dict(controller=dict(path='controller.py')),
            bindings=dict(scope=scope, workspace=workspace),
            work_order=dict(scope=dict(allowed_paths=['service/authorization']))))
        put('docs/factory/copau-f8-support-bindings-synthetic.json',
            dict(selection=dict(source_bindings=[dict(path='service/Support.java', sha256='5' * 64)])))
        return documents

    def test_sources_not_examples_determine_fence(self):
        documents = self.fixture()
        result = fence.derive(documents.__getitem__, list(documents))
        for path in ('controller.py', 'worker/input.txt', 'service/Support.java',
                     'service/TransactionService.java', 'original-judge.py', *documents):
            self.assertIn(path, result['paths'])
        self.assertEqual([], fence.violations(result, ['service/AccountRule.java']))

    def test_new_candidate_and_new_original_test_are_fenced(self):
        documents = self.fixture()
        result = fence.derive(documents.__getitem__, list(documents))
        changed = ['service/authorization/New.java',
                   'factory/carddemo-web/service/src/test/java/NewTest.java']
        self.assertEqual(sorted(changed), fence.violations(result, changed))
        self.assertEqual([], fence.violations(result, ['service/authorization-extra/Okay.java']))

    def test_additive_support_records_cannot_remove_earlier_paths(self):
        documents = self.fixture()
        path = 'docs/factory/copau-f8-support-bindings-later.json'
        documents[path] = json.dumps(dict(selection=dict(source_bindings=[
            dict(path='service/Other.java', sha256='6' * 64)]))).encode()
        result = fence.derive(documents.__getitem__, list(documents))
        self.assertIn('service/Support.java', result['paths'])
        self.assertIn('service/Other.java', result['paths'])

    def test_changed_bound_record_and_missing_record_refuse(self):
        documents = self.fixture()
        documents['workspace.json'] += b' '
        with self.assertRaisesRegex(ValueError, 'fence-record-hash'):
            fence.derive(documents.__getitem__, list(documents))
        del documents['workspace.json']
        with self.assertRaises(KeyError):
            fence.derive(documents.__getitem__, list(documents))

    def test_wrong_amendment_and_unknown_request_schema_refuse(self):
        for path, field in ((fence.AMENDMENT, 'original_manifest_sha256'), (fence.F2, 'schema')):
            documents = self.fixture()
            value = json.loads(documents[path]); value[field] = 'unreviewed'
            documents[path] = json.dumps(value).encode()
            with self.subTest(path=path), self.assertRaises(ValueError):
                fence.derive(documents.__getitem__, list(documents))

    def test_missing_support_inventory_and_unsafe_paths_refuse(self):
        documents = self.fixture()
        names = [path for path in documents if 'support-bindings' not in path]
        with self.assertRaisesRegex(ValueError, 'missing-support'):
            fence.derive(documents.__getitem__, names)
        for path in ('../outside', '/absolute', 'a\\b', 'C:/x', 'a//b'):
            with self.subTest(path=path), self.assertRaises(ValueError):
                fence.safe_path(path)

    def test_base_objects_prevent_candidate_record_tampering_and_renames(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)

            def git(*args):
                return subprocess.check_output(['git', '-C', str(root), *args]).decode().strip()

            git('init', '-q')
            git('config', 'user.name', 'Synthetic')
            git('config', 'user.email', 'synthetic@example.invalid')
            git('config', 'core.autocrlf', 'false')
            documents = self.fixture()
            for name, raw in {**documents, 'service/Support.java': b'original'}.items():
                path = root / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(raw)
            git('add', '.'); git('commit', '--no-gpg-sign', '-qm', 'base')
            base = git('rev-parse', 'HEAD')
            git('mv', 'service/Support.java', 'service/Unfenced.java')
            (root / fence.F2).write_text('{}', encoding='utf-8')
            git('add', '.'); git('commit', '--no-gpg-sign', '-qm', 'candidate')
            report = fence.inspect(root, base, 'HEAD')
            self.assertFalse(report['merge_permitted'])
            self.assertIn('service/Support.java', report['blocked_paths'])
            self.assertIn(fence.F2, report['blocked_paths'])
            self.assertFalse(report['automatic_expiry'])
            self.assertEqual(base, report['base'])

    def test_exact_current_records_derive_without_runtime_imports(self):
        root = Path(__file__).resolve().parents[1]
        report = fence.inspect(root, 'HEAD', 'HEAD')
        self.assertGreaterEqual(report['fenced_paths'], 153)
        self.assertTrue(report['merge_permitted'])
        self.assertIn(fence.F2, report['source_records'])
