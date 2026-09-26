"""Reconstruct native readbacks and recompute the published schema findings."""
from functools import lru_cache
import gzip
import hashlib
import json
from pathlib import Path
import unittest
import zipfile

from lightyear_calibration.contracts import digest, seal, verify
from lightyear_calibration.schema_equivalence import assess
from lightyear_calibration.schema_probes import compare_lanes

ROOT = Path(__file__).resolve().parents[1]/'docs/calibration/idempiere-schema'


@lru_cache(maxsize=1)
def archive(): return zipfile.ZipFile(ROOT/'evidence.zip')


def read(name): return json.loads(archive().read('evidence/'+name))


def catalog(phase, lane):
    return json.loads(gzip.decompress(archive().read(f'evidence/{phase}/{lane}-catalog.json.gz')))


def native_state(lane, phase):
    manifest = read(f'states/{lane}-{phase}.json'); verify(manifest)
    tables = {}
    for name, item in manifest['tables'].items():
        multiset = read(f"states/blobs/{item['row_multiset_sha256']}.json")
        if digest(multiset) != item['row_multiset_sha256']: raise AssertionError('Row multiset hash mismatch')
        tables[name] = dict(item['header'], row_multiset=multiset)
    result = seal(dict(manifest['header'], tables=tables))
    if result['content_sha256'] != manifest['native_state_sha256']: raise AssertionError('Native state reconstruction mismatch')
    return result


class SchemaPublicationTests(unittest.TestCase):
    @classmethod
    def tearDownClass(cls):
        archive().close(); archive.cache_clear()

    def test_archive_inventory_and_claim_boundaries(self):
        receipt = json.loads((ROOT/'receipt.json').read_text()); verify(receipt)
        self.assertEqual(receipt['evidence_archive']['sha256'], hashlib.sha256((ROOT/'evidence.zip').read_bytes()).hexdigest())
        self.assertEqual(set(receipt['evidence_files']), set(archive().namelist()))
        for name, expected in receipt['evidence_files'].items():
            self.assertEqual(expected, hashlib.sha256(archive().read(name)).hexdigest(), name)
        for claim in ('schema_equivalence', 'application_equivalence', 'platform_qualification', 'independently_attested'):
            self.assertFalse(receipt[claim])

    def test_schema_assessment_is_recomputed_from_native_catalogs(self):
        result = assess({lane: catalog('after-nullability', lane) for lane in ('oracle', 'postgresql')})
        retained = json.loads((ROOT/'assessment.json').read_text())
        self.assertEqual(retained, result)
        self.assertEqual(0, result['counts']['nullable_differences'])
        self.assertEqual(0, result['counts']['foreign_key_missing_relationships'])
        self.assertEqual(3826, result['counts']['foreign_key_catalog_matches'])
        self.assertEqual(900, result['counts']['primary_key_column_set_matches'])
        self.assertEqual(917, result['counts']['unique_key_column_set_matches'])

    def test_all_repair_readbacks_preserve_rows_and_bind_execution(self):
        preflight = read('repair-preflight.json'); verify(preflight)
        for lane in ('oracle', 'postgresql'):
            phases = ('before', 'after-foreign-keys', 'after-nullability')
            states = [native_state(lane, phase) for phase in phases]
            for previous, current, repair in zip(states, states[1:], ('foreign-key-repair', 'nullability-repair')):
                result = read(f'{repair}/{lane}-result.json'); verify(result)
                self.assertEqual(previous['content_sha256'], result['before_state_sha256'])
                self.assertEqual(current['content_sha256'], result['after_state_sha256'])
                self.assertEqual(set(previous['tables']), set(current['tables']))
                self.assertTrue(all(previous['tables'][t]['row_multiset'] == current['tables'][t]['row_multiset'] for t in previous['tables']))
                execution = read(f'{repair}/{lane}-execution.json'); verify(execution)
                count = result.get('foreign_keys_added', result.get('columns_changed'))
                self.assertEqual(count, len(execution['changes']))
            execution = read(f'nullability-repair/{lane}-execution.json')
            self.assertEqual(preflight['content_sha256'], execution['preflight_sha256'])
            self.assertEqual('follow-shared-idempiere-application-dictionary', execution['policy'])

    def test_raw_differences_and_actual_table_controls_are_retained(self):
        lanes = {lane: read(f'native-probes/{lane}-probes.json') for lane in ('oracle', 'postgresql')}
        result = compare_lanes(lanes, {lane: catalog('native-probes', lane) for lane in lanes})
        self.assertEqual(read('native-probes/comparison.json'), result)
        self.assertEqual(7, result['counts']['observed-difference'])
        self.assertEqual(0, result['counts']['inconclusive'])
        for lane in lanes:
            controls = read(f'constraint-probes/{lane}.json'); verify(controls)
            self.assertEqual(lanes[lane]['catalog_sha256'], controls['catalog_sha256'])
            self.assertEqual(30, len(controls['cases']))
            self.assertTrue(all(x['expectation_met'] for x in controls['cases']))
            self.assertTrue(all(x['before_row_sha256'] == x['after_row_sha256'] for x in controls['cases']))
            self.assertFalse(controls['application_equivalence'])


if __name__ == '__main__': unittest.main()
