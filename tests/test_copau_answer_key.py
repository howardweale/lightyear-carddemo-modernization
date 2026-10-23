"""Synthetic-only CI. No private seed, operator directory, Tower or model."""
import base64
from copy import deepcopy
from contextlib import redirect_stdout, redirect_stderr
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from tools import copau_answer_key as helper
from tools import copau_heldout_reference as reference
from tools import copau_private_prerequisites as custody


class HeldoutReferenceTests(unittest.TestCase):
    def test_original_copau_session_offline_and_seed_dependent(self):
        root = Path(__file__).resolve().parents[1]
        if os.environ.get('COPAU_SYNTHETIC_EXACT_TREE') != '1':
            # Exercise the real reference from exact Git bytes on BOTH platforms.
            # Windows checkout conversion must not relax the producer's byte seal.
            freeze = json.loads(subprocess.check_output(['git', 'show', 'HEAD:docs/factory/copau-factory-judge-freeze-2026-10-18.json'], cwd=root))
            amendment = json.loads(subprocess.check_output(['git', 'show', 'HEAD:docs/factory/copau-factory-judge-freeze-amendment-2026-10-20.json'], cwd=root))
            paths = {r['path'] for r in freeze['files']} | {r['path'] for r in amendment['files']}
            paths.add(amendment['existing_authorized_change']['path'])
            roots = ['src', 'tools', 'factory/carddemo-web', 'spec/modernization/carddemo-data',
                     'spec/modernization/carddemo-screens', 'tests/test_copau_answer_key.py',
                     'docs/factory/copau-factory-judge-freeze-2026-10-18.json',
                     'docs/factory/copau-factory-judge-freeze-amendment-2026-10-20.json']
            roots += sorted(p for p in paths if not any(p == r or p.startswith(r+'/') for r in roots))
            with tempfile.TemporaryDirectory(prefix='copau-exact-synthetic-') as temp:
                target = Path(temp); archive = target / 'source.tar'
                with archive.open('wb') as stream:
                    subprocess.run(['git', 'archive', 'HEAD', *roots], cwd=root, stdout=stream, check=True)
                with tarfile.open(archive) as packaged:packaged.extractall(target, filter='data')
                mismatches = 0
                for path in sorted(paths):
                    canonical = (target / path).read_bytes(); working = (root / path).read_bytes()
                    if canonical != working:
                        mismatches += 1
                        self.assertEqual(working.replace(b'\r\n', b'\n'), canonical, path)
                print('Synthetic reference checkout-only CRLF differences:', mismatches)
                env = dict(os.environ, COPAU_SYNTHETIC_EXACT_TREE='1', PYTHONDONTWRITEBYTECODE='1',
                           PYTHONPATH=os.pathsep.join([str(target/'src'), str(target)]))
                result = subprocess.run([sys.executable, '-B', '-m', 'unittest',
                    'tests.test_copau_answer_key.HeldoutReferenceTests.test_original_copau_session_offline_and_seed_dependent', '-v'],
                    cwd=target, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                self.assertEqual(result.returncode, 0, result.stdout)
            return
        import psycopg
        with patch.object(socket, 'create_connection', side_effect=AssertionError('network forbidden')), \
                patch.object(psycopg, 'connect', side_effect=AssertionError('database forbidden')):
            producer, _ = reference.verify_producer(root)
            with patch.object(producer, 'snapshot', side_effect=AssertionError('snapshot forbidden')), \
                    patch.object(producer.Proof, '__init__', side_effect=AssertionError('constructor forbidden')):
                first, a = reference.run_session(root, bytes(range(32)))
                second, b = reference.run_session(root, bytes(reversed(range(32))))
                replayed, replay_provenance = reference.run_session(root, bytes(range(32)))
                self.assertEqual(first, replayed)
                self.assertEqual(a['output_sha256'], replay_provenance['output_sha256'])
        self.assertGreater(a['interactions'], 10)
        self.assertTrue(first and second and set(first).isdisjoint(second))
        self.assertNotEqual(a['fixture_sha256'], b['fixture_sha256'])
        self.assertNotEqual(a['output_sha256'], b['output_sha256'])
        self.assertEqual(len(helper.windows(first)), len(first))
        for value in first:
            self.assertEqual(len(value), 40)
            self.assertEqual(helper.scan_bytes(value.encode(), first), (1, 0))
            self.assertEqual(helper.scan_bytes(base64.b64encode(value.encode()), first), (1, 0))
        self.assertEqual(a['producer'], reference.PINNED)
        self.assertEqual(a['session'], 'Proof.run.authorizations')
        self.assertEqual(len(first), 7)
        self.assertTrue(all(row['output'] == 'pautdtl1.source_sha256' and row['length'] == 40
                            and row['selection'] == 'existing-judge-computed-record-digest'
                            and row['output_sha256'][:40] in first
                            for row in a['selected_output_bindings']))

    def test_fixture_derivation_deterministic_and_domain_separated(self):
        seed = bytes(range(32)); alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
        first = reference.derive(seed, 'merchant', 22, alphabet)
        self.assertEqual(first, reference.derive(seed, 'merchant', 22, alphabet))
        self.assertNotEqual(first, reference.derive(seed, 'city', 22, alphabet))
        self.assertEqual(len(first), 22)
        self.assertTrue(set(first) <= set(alphabet))
        with self.assertRaises(custody.Refused):
            reference.derive(b'short', 'merchant', 22, alphabet)

    def test_changed_producer_refused_before_import(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            target = root / 'docs/factory/copau-factory-judge-freeze-2026-10-18.json'
            target.parent.mkdir(parents=True); target.write_bytes(b'{}')
            (target.parent / 'copau-factory-judge-freeze-amendment-2026-10-20.json').write_bytes(b'{}')
            with patch.object(reference.importlib, 'import_module') as imports, self.assertRaises(custody.Refused):
                reference.verify_producer(root)
            imports.assert_not_called()


class HeldoutCorpusTests(unittest.TestCase):
    def setUp(self):
        parent = Path(os.environ['USERPROFILE']).resolve() if os.name == 'nt' else None
        self.temp = tempfile.TemporaryDirectory(prefix='heldout-synthetic-', dir=parent)
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.index = dict(schema='copau-run-surface-index/2', captured_at='2026-10-23T00:00:00+00:00',
                          closure_review=dict(status='reviewed-complete', reference='synthetic-only'),
                          unavailable=[], corpora={}, historical=dict(status=helper.HISTORICAL,
                          catalog_sha256='0'*64, observed_count=0, missing=[], metadata_error_count=0))
        bindings = {}
        for name in ('worker', 'graph', 'prompts', 'contexts'):
            root = self.base / name; root.mkdir()
            rows = []
            for i in range(403 if name == 'worker' else 1):
                path = str(i) + '.txt'; raw = ('synthetic public ' + str(i)).encode()
                (root / path).write_bytes(raw)
                rows.append(dict(path=path, sha256=helper.sha(raw), size_bytes=len(raw), archive=False))
                if name == 'worker':
                    bindings[path] = helper.sha(raw)
            self.index['corpora'][name] = dict(root=str(root), files=rows, records=len(rows),
                                               inventory_complete=True, inventory_sha256=helper.sha(helper.encoded(rows)))
        manifest = self.base / 'manifest.json'; manifest.write_bytes(helper.encoded(bindings))
        self.index['corpora']['worker']['manifest'] = str(manifest)
        self.digest_patch = patch.object(helper, 'WORKER_SHA', helper.sha(manifest.read_bytes()))
        self.digest_patch.start(); self.addCleanup(self.digest_patch.stop)
        for name in ('graph', 'prompts', 'contexts'):
            self.index['corpora'][name].update(run_binding_sha256='1'*64, all_run_visible_content_included=True)
        history = self.base / 'history'; history.mkdir()
        self.git(history, 'init', '--quiet')
        (history / 'public.txt').write_bytes(b'synthetic public history')
        self.git(history, 'add', 'public.txt')
        self.git(history, '-c', 'user.name=Synthetic', '-c', 'user.email=synthetic@example.invalid',
                 '-c', 'commit.gpgsign=false', 'commit', '-qm', 'synthetic')
        commit = self.git(history, 'rev-parse', 'HEAD').decode().strip()
        listing = self.git(history, 'ls-tree', '-rz', '--full-tree', commit)
        self.index['corpora']['main'] = dict(root=str(history), commit=commit, tree_listing_sha256=helper.sha(listing))
        self.values = ['ABCDEFGHIJKLMNOPQRSTUVWX1234567890abcdef']
        self.assertEqual(len(self.values[0]), 40)

    @staticmethod
    def git(root, *args):
        return subprocess.check_output(['git', '-C', str(root), *args], stderr=subprocess.DEVNULL)

    def test_exact_run_surfaces_and_no_values_in_public_report(self):
        report = helper.scan_corpora(self.index, self.values)
        self.assertTrue(report['scans_clean'])
        self.assertNotIn('qualified', report)  # scanning alone does not attest seed/selection
        self.assertTrue(report['exposure_clean'] and report['collision_clean'])
        self.assertEqual(set(report['corpora']), helper.CORPORA)
        self.assertEqual(report['corpora']['worker']['file_count'], 403)
        for row in report['corpora'].values():
            self.assertEqual(row['match_count'] + row['missing_count'] + row['error_count'], 0)
            self.assertGreater(row['file_count'], 0)
        raw = helper.encoded(report)
        self.assertNotIn(self.values[0].encode(), raw)
        self.assertNotIn(str(self.base).encode(), raw)

    def test_all_window_representations_and_short_field_limit(self):
        value = self.values[0]
        for content in [value, value.lower(), ' '.join(value), base64.b64encode(value.encode()).decode(),
                        value.encode().hex(), ''.join('%%%02X' % ord(c) for c in value),
                        json.dumps(dict(answer=value)), ''.join('\\x%02x' % ord(c) for c in value)]:
            self.assertEqual(helper.scan_bytes(content.encode(), self.values), (1, 0))
        # Disclose the real limitation; never pad a short field into an answer.
        self.assertEqual(helper.scan_bytes(value[:39].encode(), self.values), (0, 0))
        self.assertEqual(helper.scan_bytes(b'x' * (helper.isolation_scan.MAX_BYTES + 1), self.values), (0, 1))

    def test_matches_missing_and_errors_each_refuse_qualification(self):
        for name in ('worker', 'graph', 'prompts', 'contexts'):
            item = self.index['corpora'][name]['files'][0]
            path = Path(self.index['corpora'][name]['root']) / item['path']
            original = path.read_bytes(); path.write_bytes(self.values[0].encode())
            report = helper.scan_corpora(self.index, self.values)
            self.assertFalse(report['scans_clean']); self.assertGreater(report['corpora'][name]['error_count'], 0)
            path.write_bytes(original)
        bad = deepcopy(self.index)
        bad['unavailable'] = [dict(corpus='contexts', kind='template', id='unreviewed-context')]
        report = helper.scan_corpora(bad, self.values)
        self.assertFalse(report['scans_clean']); self.assertEqual(report['corpora']['contexts']['missing_count'], 1)
        path = Path(self.index['corpora']['graph']['root']) / 'extra.txt'; path.write_bytes(b'extra')
        self.assertFalse(helper.scan_corpora(self.index, self.values)['scans_clean'])

    def test_actual_collision_in_valid_graph_inventory(self):
        corpus = self.index['corpora']['graph']; raw = self.values[0].encode()
        (Path(corpus['root']) / '0.txt').write_bytes(raw)
        corpus['files'][0].update(sha256=helper.sha(raw), size_bytes=len(raw))
        corpus['inventory_sha256'] = helper.sha(helper.encoded(corpus['files']))
        report = helper.scan_corpora(self.index, self.values)
        self.assertFalse(report['scans_clean']); self.assertEqual(report['corpora']['graph']['match_count'], 1)
        self.assertEqual(report['collision_count'], 1)

    def test_incomplete_inventory_and_changed_main_refused(self):
        for edit in ('review', 'graph', 'prompts', 'contexts', 'worker'):
            bad = deepcopy(self.index)
            if edit == 'review':bad['closure_review']['status'] = 'unreviewed'
            if edit in ('graph', 'prompts', 'contexts'):bad['corpora'][edit]['all_run_visible_content_included'] = False
            if edit == 'worker':bad['corpora']['worker']['files'].pop()
            with self.assertRaises(custody.Refused):helper.scan_corpora(bad, self.values)
        self.index['corpora']['main']['tree_listing_sha256'] = '0' * 64
        self.assertFalse(helper.scan_corpora(self.index, self.values)['scans_clean'])

    def test_nested_archives_paths_duplicates_and_no_extraction(self):
        def archive(rows):
            stream = io.BytesIO()
            with zipfile.ZipFile(stream, 'w') as out:
                for name, data in rows:out.writestr(name, data)
            return stream.getvalue()
        nested = archive([('inner.zip', archive([('answer.txt', self.values[0].encode())]))])
        content = list(helper.views(nested, True))
        self.assertTrue(any(helper.scan_bytes(raw, self.values)[0] for raw in content))
        for bad in [archive([('../escape', b'x')]), archive([('C:/escape', b'x')]),
                    archive([('same', b'x'), ('same', b'y')])]:
            with self.assertRaises(custody.Refused):list(helper.views(bad, True))

    def test_qualified_bundle_custody_and_unqualified_no_bundle(self):
        store = custody.Store(self.base / 'private', [self.base / 'worker'])
        store.initialize()
        root = Path(__file__).resolve().parents[1]
        provenance = dict(producer='synthetic', input_fields=['synthetic-private-input'], selected_output_bindings=[
            dict(selection='existing-judge-computed-record-digest', private_identifier_characters=15, length=40)])
        with patch.object(helper, 'run_session', return_value=(self.values, deepcopy(provenance))), \
                patch.object(helper, 'verify_current_main'):
            report, info = helper.prepare(store, root, b'Z' * 32, self.index, True)
        self.assertTrue(report['qualified'])
        self.assertEqual(info, custody.bundle_info(store.read('copau-expected-values.json')))
        self.assertEqual(set(info), {'sha256', 'size_bytes', 'count'})
        self.assertNotIn(self.values[0], json.dumps(info))
        with self.assertRaises(custody.Refused):helper.prepare(store, root, b'Z' * 32, self.index)
        other = custody.Store(self.base / 'refused', [self.base / 'worker']); other.initialize()
        bad = deepcopy(self.index); bad['unavailable'] = [dict(corpus='prompts', kind='template', id='missing-prompt')]
        with patch.object(helper, 'run_session', return_value=(self.values, deepcopy(provenance))), \
                patch.object(helper, 'verify_current_main'):
            report, info = helper.prepare(other, root, b'Z' * 32, bad, True)
        self.assertFalse(report['qualified']); self.assertIsNone(info)
        self.assertFalse(other.path('copau-expected-values.json').exists())
        self.assertTrue(other.path('heldout-provenance.json').exists())

    def test_historical_gaps_disclosed_without_gating(self):
        self.index['historical'].update(metadata_error_count=2, missing=[
            dict(kind='artifact', id=123), dict(kind='unknown-history', id='deleted-assets-unavailable')])
        report = helper.scan_corpora(self.index, self.values)
        self.assertTrue(report['scans_clean'])
        self.assertEqual(report['historical'], self.index['historical'])
        self.assertEqual(report['historical']['status'], helper.HISTORICAL)

    def test_prompts_and_contexts_are_exposure_not_collision_baseline(self):
        for name in ('prompts', 'contexts'):
            index = deepcopy(self.index); c = index['corpora'][name]; raw = self.values[0].encode()
            path = Path(c['root']) / '0.txt'; previous = path.read_bytes(); path.write_bytes(raw)
            c['files'][0].update(sha256=helper.sha(raw), size_bytes=len(raw))
            c['inventory_sha256'] = helper.sha(helper.encoded(c['files']))
            report = helper.scan_corpora(index, self.values)
            self.assertFalse(report['exposure_clean']); self.assertTrue(report['collision_clean'])
            self.assertFalse(report['scans_clean']); self.assertEqual(report['corpora'][name]['match_count'], 1)
            path.write_bytes(previous)

    def test_seed_attestation_and_public_seed_refused_before_producer(self):
        root = Path(__file__).resolve().parents[1]
        for n, (seed, confirm) in enumerate([(b'Z'*32, False), (bytes(range(32)), True), (b'short', True)]):
            store = custody.Store(self.base / ('seed-refusal-'+str(n)), [self.base / 'worker']); store.initialize()
            with patch.object(helper, 'verify_current_main'), patch.object(helper, 'run_session') as producer:
                with self.assertRaises(custody.Refused):helper.prepare(store, root, seed, self.index, confirm)
                producer.assert_not_called()
            self.assertFalse(store.path('copau-expected-values.json').exists())

    def test_live_main_change_refused_before_bundle(self):
        from tools import copau_public_corpus_index as collector
        with patch.object(collector, 'github', return_value={'object': {'sha': 'f'*40}}):
            with self.assertRaises(custody.Refused):helper.verify_current_main(self.index)

    def test_current_main_collision_rejects_even_with_clean_exposure(self):
        c = self.index['corpora']['main']; root = Path(c['root'])
        (root / 'public.txt').write_bytes(self.values[0].encode())
        self.git(root, 'add', 'public.txt')
        self.git(root, '-c', 'user.name=Synthetic', '-c', 'user.email=synthetic@example.invalid',
                 '-c', 'commit.gpgsign=false', 'commit', '-qm', 'synthetic collision')
        c['commit'] = self.git(root, 'rev-parse', 'HEAD').decode().strip()
        c['tree_listing_sha256'] = helper.sha(self.git(root, 'ls-tree', '-rz', '--full-tree', c['commit']))
        report = helper.scan_corpora(self.index, self.values)
        self.assertTrue(report['exposure_clean']); self.assertFalse(report['collision_clean'])
        self.assertEqual(report['collision_count'], 1); self.assertFalse(report['scans_clean'])

    def test_label_selection_refused_and_large_history_cannot_block(self):
        root = Path(__file__).resolve().parents[1]
        provenance = dict(selected_output_bindings=[dict(selection='label', private_identifier_characters=15, length=40)])
        store = custody.Store(self.base/'selection', [self.base/'worker']); store.initialize()
        with patch.object(helper, 'verify_current_main'), patch.object(helper, 'run_session', return_value=(self.values, provenance)):
            with self.assertRaises(custody.Refused):helper.prepare(store, root, b'Z'*32, self.index, True)
        self.assertFalse(store.path('copau-expected-values.json').exists())
        provenance['selected_output_bindings'][0]['selection'] = 'existing-judge-computed-record-digest'
        self.index['historical']['missing'] = [dict(kind='artifact', id=n+1) for n in range(20000)]
        with patch.object(helper, 'verify_current_main'), patch.object(helper, 'run_session', return_value=(self.values, provenance)):
            report, info = helper.prepare(store, root, b'Z'*32, self.index, True)
        self.assertTrue(report['qualified']); self.assertIsNotNone(info)
        self.assertEqual(len(report['historical']['missing']), 20000)
        saved = json.loads(store.read('heldout-collision-report.json'))
        self.assertEqual(saved['historical']['missing_count'], 20000)
        self.assertEqual(saved['historical']['disclosure_sha256'], helper.sha(helper.encoded(report['historical'])))

    def test_cli_failure_redacts_values(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        argv = ['helper', '--reviewed-commit', 'a'*40, '--corpus-index', 'public.json',
                '--reviewed-corpus-sha256', 'b'*64, '--exposed-root', str(self.base / 'worker')]
        with patch.object(sys, 'argv', argv), patch.object(helper, 'operate', side_effect=ValueError(self.values[0])), \
                redirect_stdout(stdout), redirect_stderr(stderr):
            self.assertEqual(helper.main(), 1)
        self.assertEqual(stdout.getvalue(), '')
        self.assertNotIn(str(self.base), stderr.getvalue())


if __name__ == '__main__':
    unittest.main()
