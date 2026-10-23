"""Manifest refusal fixtures; no new behavioral or mutation fixtures."""
from copy import deepcopy
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from tools import carddemo_account_scope as scope

ROOT = Path(__file__).resolve().parents[1]


class ParagraphScopeTests(unittest.TestCase):
    def manifest(self, index=0):
        return json.loads((ROOT / scope.PATHS[index]).read_bytes())

    def test_real_complete_inventories_counts_and_status_projection(self):
        rows = scope.load(ROOT)
        self.assertEqual([r['inventory'] for r in rows], [88, 6])
        self.assertEqual(rows[0]['counts'], {'java': 34, 'engine': 10, 'not-applicable': 44})
        self.assertEqual(rows[1]['counts'], {'java': 6, 'engine': 0, 'not-applicable': 0})
        for row in rows:
            self.assertEqual(sum(row['counts'].values()), row['inventory'])
            self.assertFalse(row['equivalence_or_mutation_proof'])
        text = scope.markdown(rows)
        self.assertIn('| COACTUPC | 88 | 34 | 10 | 44 |', text)
        self.assertIn('| COSGN00C | 6 | 6 | 0 | 0 |', text)
        inputs = scope.inputs(ROOT)
        self.assertTrue(set(scope.PATHS) <= set(inputs))
        for path in inputs:
            self.assertTrue((ROOT / path).is_file(), path)

    def test_unlisted_and_duplicate_paragraphs_refuse(self):
        for index in (0, 1):
            for duplicate in (False, True):
                manifest = self.manifest(index)
                if duplicate: manifest['paragraphs'].insert(1, deepcopy(manifest['paragraphs'][0]))
                else: manifest['paragraphs'].pop()
                with self.subTest(program=index, duplicate=duplicate), self.assertRaisesRegex(ValueError, 'exactly-once'):
                    scope.check(ROOT, manifest)

    def test_wrong_annotation_range_method_and_span_hash_refuse(self):
        for defect in ('range', 'method', 'span', 'source'):
            manifest = self.manifest()
            row = next(r for r in manifest['paragraphs'] if r['name'] == '1215-EDIT-MANDATORY')
            if defect == 'range': row['java']['annotation']['lines'] = '1825-1850'
            elif defect == 'method': row['java']['method'] = 'missingMethod'
            elif defect == 'span': row['java']['source_span_sha256'] = '0' * 64
            else: manifest['source']['sha256'] = '0' * 64
            with self.subTest(defect=defect), self.assertRaises(ValueError): scope.check(ROOT, manifest)

    def test_engine_cannot_hide_native_direct_or_nested_java_dispatch(self):
        for name in ('1215-EDIT-MANDATORY', '0000-MAIN', 'EDIT-AREA-CODE'):
            manifest = self.manifest()
            row = next(r for r in manifest['paragraphs'] if r['name'] == name)
            row.pop('java'); row.pop('covered_by', None)
            row.update(classification='engine', reason='synthetic incorrect classification')
            with self.subTest(name=name), self.assertRaises(ValueError): scope.check(ROOT, manifest)

    def test_non_applicable_cannot_hide_an_executable_engine_body(self):
        manifest = self.manifest()
        row = next(r for r in manifest['paragraphs'] if r['name'] == '3300-SETUP-SCREEN-ATTRS')
        row['classification'] = 'not-applicable'
        with self.assertRaisesRegex(ValueError, 'non-executable'): scope.check(ROOT, manifest)
        row['classification'] = 'engine'; row['reason'] = ''
        with self.assertRaisesRegex(ValueError, 'paragraph-reason'): scope.check(ROOT, manifest)

    def test_routing_source_changes_require_explicit_manifest_review(self):
        manifest = self.manifest()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in scope.inputs(ROOT):
                target = root / name; target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / name, target)
            self.assertEqual(scope.check(root, manifest)['inventory'], 88)
            target = root / scope.JAVA / 'SourceEdits.java'
            target.write_bytes(target.read_bytes() + b'\n// changed routing snapshot\n')
            with self.assertRaisesRegex(ValueError, 'routing-source-changed'): scope.check(root, manifest)
            manifest['routing_sources'].pop(scope.JAVA + 'SourceEdits.java')
            with self.assertRaisesRegex(ValueError, 'routing-binding-closure'): scope.check(root, manifest)

    def test_repeatable_annotations_and_comments_are_distinguished(self):
        text = (ROOT / scope.JAVA / 'AccountUpdateService.java').read_text()
        found = scope.java_annotations(text)
        names = {r['paragraph'] for r in found if r['method'] == 'interact'}
        self.assertEqual(names, {'0000-MAIN', '1000-PROCESS-INPUTS', '2000-DECIDE-ACTION'})
        fake = '@CobolSource(program="COACTUPC", paragraph="FAKE", lines="1-2") public void fake() {}'
        self.assertEqual(scope.java_annotations('/* ' + fake + ' */'), [])
        self.assertEqual(scope.java_annotations('// ' + fake), [])

    def test_partial_manifest_installation_refuses_but_historical_fixture_is_supported(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertIsNone(scope.load(root))
            target = root / scope.PATHS[0]; target.parent.mkdir(parents=True)
            shutil.copyfile(ROOT / scope.PATHS[0], target)
            with self.assertRaisesRegex(ValueError, 'both-program'): scope.load(root)


if __name__ == '__main__':
    unittest.main()
