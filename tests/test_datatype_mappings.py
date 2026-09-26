import gzip
import json
from pathlib import Path
import unittest
import zipfile

from lightyear_calibration.contracts import CalibrationError
from lightyear_calibration.datatype_mappings import assess, classify


class DatatypeMappingTests(unittest.TestCase):
    def test_unspecified_precision_is_not_zero_or_equivalent(self):
        r = classify({'data_type': 'NUMBER', 'data_precision': None, 'data_scale': None},
                     {'data_type': 'numeric', 'numeric_precision': None, 'numeric_scale': None})
        self.assertEqual('unbounded-or-partially-declared-numeric', r['declared_relation'])
        self.assertIn('significant-digit-and-exponent-boundaries', r['required_behavior_checks'])
        self.assertFalse(r['behavior_verified'])

    def test_equal_parameters_keep_rounding_and_overflow_obligations(self):
        r = classify({'data_type': 'NUMBER', 'data_precision': 10, 'data_scale': 2},
                     {'data_type': 'numeric', 'numeric_precision': 10, 'numeric_scale': 2})
        self.assertEqual('matching-declared-precision-and-scale', r['declared_relation'])
        self.assertIn('positive-and-negative-rounding-ties', r['required_behavior_checks'])
        self.assertIn('overflow-rejection', r['required_behavior_checks'])
        self.assertFalse(r['behavior_verified'])

    def test_different_precision_and_negative_scale_are_retained(self):
        r = classify({'data_type': 'NUMBER', 'data_precision': 8, 'data_scale': -2},
                     {'data_type': 'numeric', 'numeric_precision': 8, 'numeric_scale': 0})
        self.assertEqual('different-declared-precision-or-scale', r['declared_relation'])

    def test_byte_length_cannot_become_character_length(self):
        for unit in ('B', None):
            r = classify({'data_type': 'VARCHAR2', 'char_length': 12, 'char_used': unit},
                         {'data_type': 'character varying', 'character_maximum_length': 12})
            self.assertEqual('different-or-unknown-length-contract', r['declared_relation'])
        self.assertIn('multibyte-byte-capacity', classify(
            {'data_type': 'CHAR', 'char_length': 1, 'char_used': 'B'},
            {'data_type': 'character', 'character_maximum_length': 1})['required_behavior_checks'])

    def test_matching_text_length_keeps_empty_and_collation_obligations(self):
        r = classify({'data_type': 'VARCHAR2', 'char_length': 120, 'char_used': 'C'},
                     {'data_type': 'character varying', 'character_maximum_length': 120})
        self.assertIn('empty-string-and-null', r['required_behavior_checks'])
        self.assertIn('collation-and-comparison', r['required_behavior_checks'])

    def test_temporal_uuid_json_and_large_object_mappings_are_not_promoted(self):
        cases = [('DATE', 'timestamp without time zone', 'fractional-second-write-and-readback'),
                 ('VARCHAR2', 'uuid', 'invalid-uuid-rejection'),
                 ('CLOB', 'jsonb', 'duplicate-json-keys'),
                 ('CLOB', 'json', 'actual-column-json-constraints'),
                 ('BLOB', 'oid', 'large-object-dereference')]
        for a, b, obligation in cases:
            with self.subTest(a=a, b=b):
                r = classify({'data_type': a}, {'data_type': b})
                self.assertIn(obligation, r['required_behavior_checks'])
                self.assertFalse(r['behavior_verified'])

    def test_unknown_type_stays_unclassified(self):
        r = classify({'data_type': 'FUTURE_TYPE'}, {'data_type': 'text'})
        self.assertEqual(['unclassified-native-domain'], r['required_behavior_checks'])

    def test_complete_native_inventory_replays_offline(self):
        root = Path(__file__).resolve().parents[1]
        with zipfile.ZipFile(root/'docs/calibration/idempiere-schema/evidence.zip') as z:
            catalogs = {lane: json.loads(gzip.decompress(z.read(
                f'evidence/after-nullability/{lane}-catalog.json.gz'))) for lane in ('oracle', 'postgresql')}
        r = assess(catalogs)
        self.assertEqual(18852, r['common_column_count'])
        self.assertEqual(18852, sum(r['mapping_counts'].values()))
        self.assertEqual(2259, r['mapping_counts']['DATE -> timestamp without time zone'])
        self.assertEqual(0, r['behavior_verified_column_count'])
        self.assertTrue(all(not c['behavior_verified'] for c in r['columns']))
        price = next(c for c in r['columns'] if (c['table'], c['column']) == ('c_orderline', 'priceactual'))
        self.assertIsNone(price['native_declarations']['oracle']['data_precision'])
        self.assertEqual('unbounded-or-partially-declared-numeric', price['declared_relation'])
        catalogs['oracle']['content_sha256'] = '0'*64
        with self.assertRaises(CalibrationError): assess(catalogs)


if __name__ == '__main__': unittest.main()
