"""Synthetic CI evidence only. No VM, retained export, database or model access."""
from copy import deepcopy
import json
import subprocess
import sys
import unittest
from unittest.mock import patch
import zipfile
from cryptography.exceptions import InvalidSignature

from tests import test_tsql_r9_export as fixtures
from tools import export_tsql_r9 as export
from tools import reverify_tsql_r9 as review


class R9ReverificationTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.R9ExportTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root

    def package(self):
        f = self.fixture
        out = self.root / 'export'
        out.mkdir()
        inspected = export.inspect(f.run)
        (out / 'inspection.json').write_bytes(export.canonical(inspected))
        export.package(f.run, out, inspected['identifiers_sha256'])
        manifest = json.loads((out / 'export-manifest.json').read_bytes())
        return out, manifest

    def approval(self):
        digest = 'a' * 64
        comment = dict(user=dict(login='howardweale'),
            issue_url='https://api.github.com/repos/' + review.REPOSITORY + '/issues/423',
            body='Reviewed ' + review.TAG + ' ' + export.PACKAGE + ' SHA-256 ' + digest)
        assets = [dict(id=i, name=n, size=100, state='uploaded', digest='sha256:' + digest,
            browser_download_url='https://github.com/' + review.REPOSITORY + '/releases/download/' + review.TAG + '/' + n)
            for i, n in enumerate((export.PACKAGE, 'export-manifest.json'), 1)]
        release = dict(tag_name=review.TAG, draft=False, prerelease=False, assets=assets)
        return release, comment, digest

    def test_requires_exact_public_release_and_Howard_asset_digest_post(self):
        release, comment, digest = self.approval()
        self.assertEqual(set(review.approved_assets(release, comment, digest)), {export.PACKAGE, 'export-manifest.json'})
        for key, value in [('user', {'login': 'someone-else'}), ('body', export.PACKAGE),
                           ('issue_url', comment['issue_url'].replace('/423', '/415'))]:
            changed = deepcopy(comment); changed[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                review.approved_assets(release, changed, digest)
        for change in ('draft', 'duplicate', 'digest', 'url', 'size'):
            altered = deepcopy(release)
            if change == 'draft': altered['draft'] = True
            elif change == 'duplicate': altered['assets'].append(altered['assets'][0])
            elif change == 'digest': altered['assets'][0]['digest'] = 'sha256:' + 'b' * 64
            elif change == 'url': altered['assets'][0]['browser_download_url'] = 'https://example.test/package'
            else: altered['assets'][0]['size'] = export.MAX_TOTAL * 2
            with self.subTest(change=change), self.assertRaises(ValueError):
                review.approved_assets(altered, comment, digest)

    def test_roundtrip_verifies_every_original_signed_byte_without_rewriting(self):
        f = self.fixture
        before = {p.relative_to(f.run).as_posix(): p.read_bytes() for p in f.run.rglob('*') if p.is_file()}
        with f.guard():
            out, manifest = self.package()
            result = review.unpack(out / export.PACKAGE, out / 'export-manifest.json',
                                   manifest['package_sha256'], self.root / 'verified')
            self.assertEqual(result['native_pairs'], 108)
            self.assertEqual(result['signed_file_count'], len(f.files))
            after = {p.relative_to(self.root / 'verified').as_posix(): p.read_bytes()
                     for p in (self.root / 'verified').rglob('*') if p.is_file()}
            self.assertEqual(before, after)
            self.assertEqual(before, {p.relative_to(f.run).as_posix(): p.read_bytes()
                                     for p in f.run.rglob('*') if p.is_file()})
            with self.assertRaises(FileExistsError):
                review.unpack(out / export.PACKAGE, out / 'export-manifest.json',
                              manifest['package_sha256'], self.root / 'verified')

    def test_outer_hash_inner_hash_closure_and_signature_refusals(self):
        f = self.fixture
        with f.guard():
            out, manifest = self.package()
            original = (out / export.PACKAGE).read_bytes()
            with self.assertRaisesRegex(ValueError, 'package-digest'):
                review.unpack(out / export.PACKAGE, out / 'export-manifest.json', '0' * 64, self.root / 'bad')
            with zipfile.ZipFile(out / export.PACKAGE) as z:
                members = [(i, z.read(i)) for i in z.infolist()]
            for mode in ('extra', 'duplicate', 'file-hash', 'signature', 'symlink', 'traversal'):
                package = self.root / (mode + '.zip')
                changed_manifest = deepcopy(manifest)
                with zipfile.ZipFile(package, 'w') as z:
                    for info, raw in members:
                        info = deepcopy(info)
                        if info.filename == 'revision-9/report.json':
                            if mode == 'file-hash': raw += b' '
                            if mode == 'signature':
                                data = json.loads(raw); data['signature'] = 'A' * 88
                                raw = export.canonical(data)
                                changed_manifest['files']['report.json'] = dict(bytes=len(raw), sha256=export.sha(raw))
                            if mode == 'symlink': info.external_attr = 0o120777 << 16
                            if mode == 'traversal': info.filename = 'revision-9/../report.json'
                        z.writestr(info, raw)
                    if mode == 'extra': z.writestr('revision-9/extra.json', b'{}')
                    if mode == 'duplicate': z.writestr(members[0][0], members[0][1])
                changed_manifest.update(package_sha256=review.file_sha(package), package_bytes=package.stat().st_size,
                    total_bytes=sum(v['bytes'] for v in changed_manifest['files'].values()))
                path = self.root / (mode + '.json'); path.write_bytes(export.canonical(changed_manifest))
                with self.subTest(mode=mode), self.assertRaises((ValueError, InvalidSignature)):
                    review.unpack(package, path, changed_manifest['package_sha256'], self.root / ('unpack-' + mode))
            self.assertEqual((out / export.PACKAGE).read_bytes(), original)

    def test_recursive_contract_diff_retains_types_missing_values_and_outcomes(self):
        old = {'a/b': {'x~y': [1, None]}, 'absent': None, 'type': True}
        current = {'a/b': {'x~y': [2, None]}, 'type': 1}
        changes = review.differences(old, current)
        self.assertEqual({r['path'] for r in changes}, {'/a~1b/x~0y/0', '/absent', '/type'})
        self.assertFalse(next(r for r in changes if r['path'] == '/absent')['current_present'])

    def test_current_parser_contract_and_comparator_refusals_remain_visible(self):
        from lightyear_data.tsql_procedures import semantics, comparison_v9
        target = dict(observation=dict(target_source="SELECT 'LIMIT 1' AS x"))
        source = dict(observation=dict(source_syntax={}))
        actual = semantics.target_contract(target['observation']['target_source'])
        self.assertFalse(actual['policy_obligations'])
        saved = dict(mapping={}, observed_status='match-on-compared-observables', verdict='equivalent',
                     syntax_contract={}, target_syntax_contract=actual)
        with patch.object(semantics, 'contract', return_value={}), \
                patch.object(semantics, 'resolve_results', return_value={}), \
                patch.object(comparison_v9, 'compare', return_value=deepcopy(saved)):
            self.assertEqual(review.compare_pair(source, target, saved)['status'], 'unchanged')
            changed = deepcopy(saved); changed['target_syntax_contract']['policy_obligations'] = ['new-obligation']
            changed['verdict'] = 'insufficient-evidence'
            with patch.object(comparison_v9, 'compare', return_value=changed):
                row = review.compare_pair(source, target, saved)
                self.assertEqual(row['status'], 'changed'); self.assertTrue(row['outcome_changed'])
                self.assertTrue(row['contract_changes']); self.assertEqual(row['original_comparison'], saved)
            with patch.object(comparison_v9, 'compare', side_effect=ValueError('coverage-binding')):
                row = review.compare_pair(source, target, saved)
                self.assertEqual(row['status'], 'refused'); self.assertEqual(row['error'], 'coverage-binding')
                self.assertEqual(row['contracts']['target_syntax_contract'], actual)
            with patch.object(semantics, 'target_contract', side_effect=ValueError('parser-refusal')):
                row = review.compare_pair(source, target, saved)
                self.assertEqual(row['status'], 'refused')
                self.assertEqual(row['contract_errors']['target_syntax_contract']['message'], 'parser-refusal')

    def full_fixture(self):
        f = self.fixture
        qualification = dict(images={}, bridge_sha256='bridge')
        f.store('coverage-qualification.json', export.canonical(qualification))
        plan = dict(comparison_revision=9, owner='synthetic', pairs=108, ids=['fixture'], images={},
                    coverage_qualification_sha256=f.files['coverage-qualification.json'], coverage_bridge_sha256='bridge')
        f.store('plan.json', f.signed(plan))
        f.store('ready.json', f.signed(dict(images={})))
        f.store('m0-acceptance.json', f.signed(dict(schema='tsql-M0-acceptance/5', passed=True,
            procedures=43, native_pairs=108, variants=[dict(accepted=True) for _ in range(86)])))
        assets = {n: dict(sha256='a' * 64) for n in ('source', 'correct', 'source-setup', 'target-setup')}
        capture = dict(baseline=dict(procedure_sha256='a' * 64, setup_sha256='a' * 64), observation={})
        saved = dict(schema='tsql-native-comparison/9', mapping=dict(assets=assets),
                     coverage_qualification=qualification, observed_status='match-on-compared-observables', verdict='equivalent')
        records = []
        for index in range(1, 109):
            folder = f'pair-{index:03d}-fixture-correct-1'
            record = dict(index=index, id='fixture', variant='correct', repeat=1,
                          status=saved['observed_status'], verdict=saved['verdict'])
            files = {}
            for name, value in [('source.json', capture), ('target.json', capture), ('comparison.json', saved)]:
                raw = export.canonical(value); f.store(folder + '/' + name, raw); files[name] = export.sha(raw)
            body = dict(record, schema='tsql-native-pair/1', model_calls=0, files=files, assets=assets,
                        plan_sha256=f.files['plan.json'], images={})
            manifest = f.signed(body); f.store(folder + '/manifest.json', manifest)
            record['manifest_sha256'] = json.loads(manifest)['content_sha256']
            f.store(f'progress-{index:03d}.json', f.signed(record))
            f.store(f'replay-{index:03d}.json', f.signed(dict(manifest_sha256=record['manifest_sha256'], comparison=saved)))
            records.append(record)
        f.body.update(owner='synthetic', planned_pairs=108, records=records,
                      counts={'match-on-compared-observables': 108})
        f.reseal()
        return plan, qualification

    def test_all_108_reports_survive_a_changed_pair_and_a_refusal(self):
        self.full_fixture(); f = self.fixture
        from tools import replay_tsql_native
        outcomes = [dict(status='unchanged') for _ in range(108)]
        outcomes[0] = dict(status='changed', changes=[dict(path='/verdict', old='equivalent', current='divergent')])
        outcomes[1] = dict(status='refused', error='synthetic-parser-refusal')
        original = {p: review.file_sha(p) for p in f.run.rglob('*') if p.is_file()}
        with f.guard(), patch.object(review, 'compare_pair', side_effect=outcomes) as compare, \
                patch.object(replay_tsql_native, 'audit') as audit:
            summary = review.replay(f.run, self.root / 'results', {})
            self.assertEqual(compare.call_count, 108); audit.assert_not_called()
            self.assertEqual(summary['pair_counts'], {'changed': 1, 'refused': 1, 'unchanged': 106})
            self.assertFalse(summary['holds_under_pglast_7_20']); self.assertEqual(len(summary['pairs']), 108)
            for row in summary['pairs']:
                self.assertEqual(review.file_sha(self.root / 'results' / row['report']), row['report_sha256'])
        self.assertEqual(original, {p: review.file_sha(p) for p in original})

    def test_unchanged_requires_original_audit_and_authentication_precedes_comparison(self):
        plan, qualification = self.full_fixture(); f = self.fixture
        from tools import replay_tsql_native
        with f.guard(), patch.object(review, 'compare_pair', return_value=dict(status='unchanged')), \
                patch.object(replay_tsql_native, 'audit', return_value=dict(qualification_passed=True)):
            self.assertTrue(review.replay(f.run, self.root / 'pass', {})['holds_under_pglast_7_20'])
        with f.guard(), patch.object(review, 'compare_pair', return_value=dict(status='unchanged')), \
                patch.object(replay_tsql_native, 'audit', side_effect=ValueError('original-audit-refusal')):
            summary = review.replay(f.run, self.root / 'refusal', {})
            self.assertFalse(summary['holds_under_pglast_7_20'])
            self.assertEqual(summary['audit_error']['message'], 'original-audit-refusal')
        record = f.body['records'][0]
        progress = f.run / 'progress-001.json'; original = progress.read_bytes()
        progress.write_bytes(original.replace(b'fixture', b'changed'))
        with self.assertRaises((ValueError, InvalidSignature)):
            review.pair_inputs(f.run, record, f.public, plan, qualification)
        progress.write_bytes(original)
        review.pair_inputs(f.run, record, f.public, plan, qualification)

    def test_offline_guard_blocks_network_and_process_creation_in_fresh_interpreter(self):
        code = '''
import socket, subprocess
from tools.reverify_tsql_r9 import offline_guard
offline_guard()
for operation in (lambda: socket.socket(), lambda: subprocess.run(['should-never-start'])):
    try:
        operation()
    except RuntimeError as failure:
        assert str(failure) == 'offline-replay-forbids-network-and-processes'
    else:
        raise AssertionError('offline boundary escaped')
'''
        subprocess.run([sys.executable, '-c', code], check=True)


if __name__ == '__main__':
    unittest.main()
