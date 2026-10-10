import copy
import hashlib
import json
from pathlib import Path
import unittest

from tools.b06_host_probe.recorded_prefix import replay_projection, structural_fixture

ROOT = Path(__file__).parent / 'fixtures/b06-generation-prefix'
PINS = {'r1': '3a2548ac3a8477aa82b86229a1266538d026107a3b4096c50efee7d40f893993',
        'r2': 'bec10785e794dbaa1f51c6ae941b408268f210c328df755b43b350a7bdebdb74'}


class RecordedPrefixTests(unittest.TestCase):
    def fixture(self, name):
        data = (ROOT / (name + '.json')).read_bytes()
        self.assertEqual(hashlib.sha256(data).hexdigest(), PINS[name])
        return json.loads(data)

    def test_both_authenticated_derived_prefixes_keep_incompleteness_explicit(self):
        for name, count, opens in [('r1', 24827, 4), ('r2', 24870, 3)]:
            with self.subTest(name=name):
                fixture = self.fixture(name)
                replay = replay_projection(fixture)
                self.assertEqual(fixture['event_count'], count)
                self.assertEqual(sum(map(len, replay['open_calls'].values())), opens)
                self.assertTrue(replay['recorded_pairing_passed'])
                self.assertFalse(replay['exact_exception_reproduced'])
                self.assertFalse(replay['tracker_fix_proven'])
                self.assertIsNone(replay['unrecorded_failure_event_index'])
                self.assertIn('request identity', replay['missing_fields'])

    def test_changed_return_and_reordered_entries_refuse(self):
        original = self.fixture('r2')
        for mutation in ('return', 'order'):
            fixture = copy.deepcopy(original)
            if mutation == 'return':
                next(r for r in fixture['events'] if r[1] == 'generation-return')[4] += 1
            else:
                fixture['events'][1][0] = fixture['events'][0][0]
            with self.assertRaises(ValueError):
                replay_projection(fixture)

    def test_export_discards_values_names_and_stacks(self):
        result = dict(source_event_sha256='a'*64, census_sha256='b'*64,
                      failure_sha256='c'*64, counts={}, event_count=1, missing_fields=[],
                      events=[dict(index=1, kind='generation-entry', thread=1,
                                   method='java.lang.ClassLoader.defineClass()V', depth=2,
                                   stack=['PRIVATE'], value='PRIVATE', thread_name='PRIVATE')])
        value = structural_fixture(result, 'd'*40, 'e'*64)
        self.assertNotIn('PRIVATE', json.dumps(value))
        self.assertEqual(len(value['events'][0]), 5)
