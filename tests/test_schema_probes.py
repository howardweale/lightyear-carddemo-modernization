"""Probe failures, stale catalogs and weaker evidence must never become passes."""
from copy import deepcopy
import unittest

from lightyear_calibration.contracts import CalibrationError, digest, seal
from lightyear_calibration.schema_probes import compare_lanes, compare_outcomes, definitions
from tests.test_schema_equivalence import captured


def reseal(value):
    return seal({k: v for k, v in value.items() if k != "content_sha256"})


def fixtures():
    catalogs = {lane: captured(lane) for lane in ('oracle', 'postgresql')}
    lanes = {lane: seal({
        'artifact_type': 'lightyear-native-schema-probe-lane', 'lane': lane,
        'evidence_class': 'native-database-observation', 'catalog_sha256': catalog['content_sha256'],
        'plan_sha256': digest(definitions()), 'clock_observation': {},
        'cases': [{'case_id': case['id'], 'family': case['family'],
                   'sql_sha256': digest(case['sql'][lane]),
                   'outcome': {'status': 'observed-value', 'value': 1}} for case in definitions()]
    }) for lane, catalog in catalogs.items()}
    return lanes, catalogs


class SchemaProbeTests(unittest.TestCase):
    def test_value_types_and_unknown_errors_do_not_compare_equal(self):
        value = lambda x: {'status': 'observed-value', 'value': x}
        self.assertEqual('observed-difference', compare_outcomes(value(True), value(1)))
        error = {'status': 'probe-error', 'error_class': None}
        self.assertEqual('inconclusive', compare_outcomes(error, error))
        self.assertEqual('observed-difference', compare_outcomes(value(None), value('')))

    def test_complete_observations_do_not_promote_full_schema(self):
        result = compare_lanes(*fixtures())
        self.assertEqual(20, result['counts']['observed-match'])
        self.assertFalse(result['schema_equivalence'])
        self.assertFalse(result['application_equivalence'])
        self.assertFalse(result['independently_attested'])

    def test_malformed_case_inventory_or_plan_is_rejected(self):
        for mutation in ('missing', 'duplicate', 'sql', 'family', 'status', 'plan'):
            lanes, catalogs = fixtures()
            item = lanes['oracle']
            if mutation == 'missing': item['cases'].pop()
            if mutation == 'duplicate': item['cases'][1] = deepcopy(item['cases'][0])
            if mutation == 'sql': item['cases'][0]['sql_sha256'] = '0' * 64
            if mutation == 'family': item['cases'][0]['family'] = 'uuid'
            if mutation == 'status': item['cases'][0]['outcome']['status'] = 'passed'
            if mutation == 'plan': item['plan_sha256'] = '0' * 64
            lanes['oracle'] = reseal(item)
            with self.subTest(mutation=mutation), self.assertRaises(CalibrationError):
                compare_lanes(lanes, catalogs)

    def test_catalog_and_native_evidence_bindings_are_required(self):
        for mutation in ('seal', 'catalog-hash', 'catalog-lane', 'baseline', 'simulated', 'artifact'):
            lanes, catalogs = fixtures()
            if mutation == 'seal': lanes['oracle']['lane'] = 'postgresql'
            elif mutation == 'catalog-hash':
                lanes['oracle'] = reseal(dict(lanes['oracle'], catalog_sha256='0' * 64))
            elif mutation == 'catalog-lane': catalogs['oracle'] = catalogs['postgresql']
            elif mutation == 'baseline':
                catalogs['oracle']['import_binding']['ms84_checkpoint_sha256'] = 'd' * 64
                catalogs['oracle'] = reseal(catalogs['oracle'])
                lanes['oracle'] = reseal(dict(lanes['oracle'], catalog_sha256=catalogs['oracle']['content_sha256']))
            elif mutation == 'simulated':
                lanes['oracle'] = reseal(dict(lanes['oracle'], evidence_class='simulated'))
            elif mutation == 'artifact':
                lanes['oracle'] = reseal(dict(lanes['oracle'], artifact_type='other'))
            with self.subTest(mutation=mutation), self.assertRaises(CalibrationError):
                compare_lanes(lanes, catalogs)

    def test_only_allowlisted_native_rejections_can_match(self):
        lanes, catalogs = fixtures()
        for lane, code in [('oracle', 1438), ('postgresql', '22003')]:
            lanes[lane]['cases'][0]['outcome'] = {
                'status': 'observed-rejection', 'native_code': code, 'error_class': 'numeric-overflow'}
            lanes[lane] = reseal(lanes[lane])
        self.assertEqual(1, compare_lanes(lanes, catalogs)['counts']['observed-matching-rejection'])
        lanes['oracle']['cases'][0]['outcome']['native_code'] = 99999
        lanes['oracle'] = reseal(lanes['oracle'])
        with self.assertRaises(CalibrationError): compare_lanes(lanes, catalogs)


if __name__ == '__main__':
    unittest.main()
