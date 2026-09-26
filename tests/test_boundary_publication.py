"""Replay native boundary findings and the separately bounded operations result."""
import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from lightyear_calibration import boundary_journey, operations_journey
from lightyear_calibration.application_effects import admit
from lightyear_calibration.application_journey import read_trace
from lightyear_calibration.contracts import canonical, digest, seal, verify, CalibrationError
from lightyear_calibration.datatype_mappings import assess
from lightyear_calibration.native_reconciliation import state, rows

ROOT = Path(__file__).resolve().parents[1]/'docs/calibration/idempiere-boundaries'


class BoundaryPublicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.archive = zipfile.ZipFile(ROOT/'evidence.zip'); cls.addClassCleanup(cls.archive.close)
        cls.temp = tempfile.TemporaryDirectory(); cls.addClassCleanup(cls.temp.cleanup)
        cls.workspace = Path(cls.temp.name)

    @classmethod
    def read(cls, name): return json.loads(cls.archive.read('evidence/'+name))

    @classmethod
    def snapshot(cls, case, label, lane):
        manifest = cls.read(f'{case}/states/{label}-{lane}.json'); verify(manifest)
        tables = {}
        for table, item in manifest['tables'].items():
            multiset = cls.read(f"states/blobs/{item['row_multiset_sha256']}.json")
            if digest(multiset) != item['row_multiset_sha256']: raise AssertionError('Changed row-hash multiset')
            tables[table] = dict(item['header'], row_multiset=multiset)
        native = seal(dict(manifest['header'], tables=tables))
        if native['content_sha256'] != manifest['native_state_sha256']: raise AssertionError('Changed native state')
        folder = cls.workspace/case/label/lane; folder.mkdir(parents=True, exist_ok=True)
        (folder/'state.json').write_bytes(canonical(native))
        prefix = f'evidence/{case}/rows/{label}/{lane}/'
        for name in cls.archive.namelist():
            if name.startswith(prefix):
                target = (folder/name[len(prefix):]).resolve()
                if not target.is_relative_to(folder.resolve()): raise AssertionError('Unsafe archive path')
                target.write_bytes(cls.archive.read(name))
        return folder

    def test_archive_claims_and_cleanup(self):
        receipt = json.loads((ROOT/'receipt.json').read_text()); verify(receipt)
        self.assertEqual(receipt['evidence_archive']['sha256'], hashlib.sha256((ROOT/'evidence.zip').read_bytes()).hexdigest())
        self.assertEqual(set(receipt['evidence_files']), set(self.archive.namelist()))
        for name, expected in receipt['evidence_files'].items():
            self.assertEqual(expected, hashlib.sha256(self.archive.read(name)).hexdigest(), name)
        self.assertFalse(receipt['bounded_boundary_equivalence'])
        self.assertTrue(receipt['bounded_operations_equivalence'])
        for claim in ('first_only_locking_api_qualified', 'schema_equivalence', 'application_equivalence',
                      'platform_qualification', 'independently_attested', 'cloud_resources_started'):
            self.assertFalse(receipt[claim])
        self.assertEqual(6, receipt['native_application_executions'])
        self.assertEqual(2, receipt['diagnostic_native_application_executions'])
        cleanup = json.loads((ROOT/'cleanup.json').read_text()); verify(cleanup)
        self.assertEqual(receipt['cleanup_sha256'], cleanup['content_sha256'])
        self.assertTrue(cleanup['all_experiment_containers_stopped'])
        self.assertEqual(6, len(cleanup['containers']))
        self.assertTrue(all(not x['running'] and x['data_retained'] for x in cleanup['containers']))

    def test_native_business_outcomes_rules_and_failed_timestamp_recompute(self):
        prior = self.read('ms84-checkpoint.json')
        for case, verifier, harness_name in [('fractional', boundary_journey, 'LightyearBoundaryTest.java'),
                                             ('operations', operations_journey, 'LightyearOperationsTest.java')]:
            with self.subTest(case=case):
                folders = {lane: self.snapshot(case, 'after', lane) for lane in ('oracle','postgresql')}
                before = {lane: self.snapshot(case, 'before', lane) for lane in folders}
                executions = {lane: self.read(f'{case}/{lane}/execution.json') for lane in folders}
                effects = admit(self.read(f'{case}/final/base-checkpoint.json'), folders, before,
                                self.read(f'{case}/final/primary-keys.json'), executions, prior_checkpoint=prior)
                self.assertEqual(self.read(f'{case}/final/effect-checkpoint.json'), effects)
                results = {}
                for lane in folders:
                    trace = self.workspace/(case+'-'+lane+'.xml')
                    trace.write_bytes(self.archive.read(f'evidence/{case}/{lane}/journey.xml'))
                    result = verifier.verify_lane(folders[lane], trace, executions[lane], (ROOT/harness_name).read_bytes())
                    self.assertEqual(self.read(f'{case}/final/{lane}-verified-journey.json'), result)
                    results[lane] = result
                compared = verifier.compare_lanes(results, effects)
                self.assertEqual(json.loads((ROOT/(case+'-comparison.json')).read_text()), compared)
                if case == 'fractional':
                    self.assertEqual({'oracle':14, 'postgresql':15}, compared['passed_check_count'])
                    self.assertFalse(compared['bounded_boundary_equivalence'])
                    self.assertEqual(1, len(effects['unresolved_differences']))
                    self.assertEqual('shipdate', effects['unresolved_differences'][0]['column'])
                    forged = dict(effects); forged['state_sha256'] = {'oracle':'changed','postgresql':'changed'}
                    with self.assertRaises(CalibrationError): verifier.compare_lanes(results, seal(forged))
                else:
                    self.assertTrue(compared['bounded_operations_equivalence'])
                    self.assertFalse(effects['unresolved_differences'])

    def test_separate_fresh_baselines_and_datatype_inventory(self):
        for lane in ('oracle','postgresql'):
            a = state(self.snapshot('fractional','before',lane),lane)
            b = state(self.snapshot('operations','before',lane),lane)
            self.assertEqual(set(a['tables']),set(b['tables']))
            self.assertTrue(all(a['tables'][t]['row_multiset'] == b['tables'][t]['row_multiset'] for t in a['tables']))
        catalogs = {lane: json.loads(gzip.decompress(self.archive.read(
            f'evidence/fractional/baseline/{lane}-catalog.json.gz'))) for lane in ('oracle','postgresql')}
        result = assess(catalogs)
        self.assertEqual(json.loads((ROOT/'mappings.json').read_text()), result)
        self.assertEqual(18852,result['common_column_count'])
        self.assertEqual(1023,result['declared_relation_counts']['unbounded-or-partially-declared-numeric'])

    def test_failed_first_only_api_cannot_inherit_the_alternative_result(self):
        for lane, code in [('oracle',1),('postgresql',0)]:
            execution = self.read(f'diagnostic-first-only/{lane}/execution.json'); verify(execution)
            self.assertEqual(code, execution['exit_code'])
            harness = self.archive.read(f'evidence/diagnostic-first-only/{lane}/harness.java')
            self.assertEqual(execution['harness_sha256'], hashlib.sha256(harness).hexdigest())
            self.assertIn(b'.setForUpdate(true).firstOnly()', harness)
        excerpt = self.read('diagnostic-first-only/oracle/error-excerpt.json'); verify(excerpt)
        self.assertTrue(any('ORA-03049' in line and 'FETCH' in line for line in excerpt['lines']))
        folder = self.snapshot('diagnostic-first-only','after','oracle')
        snapshot = state(folder,'oracle'); issues = rows(folder,snapshot['tables']['ad_issue'])
        self.assertTrue(any('ORA-03049' in json.dumps(row) for row in issues))
        self.assertNotIn(b'.setForUpdate(true).firstOnly()', (ROOT/'LightyearOperationsTest.java').read_bytes())
        self.assertIn(b'.setForUpdate(true).list()', (ROOT/'LightyearOperationsTest.java').read_bytes())


if __name__ == '__main__': unittest.main()
