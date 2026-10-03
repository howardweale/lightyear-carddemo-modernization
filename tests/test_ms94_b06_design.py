import unittest
from datetime import datetime, timedelta, timezone
from tools.ms94_b06_design import schedule, calendar, calendar_guard, analysis


class B06DesignTests(unittest.TestCase):
    def test_schedule_balanced_random_blocks_and_excluded_pilots(self):
        value = schedule('ab' * 32)
        self.assertEqual(value, schedule('ab' * 32))
        self.assertNotEqual(value['slots'], schedule('cd' * 32)['slots'])
        slots = value['slots']
        self.assertEqual(78, len(slots))
        self.assertEqual(78, len({x['id'] for x in slots}))
        self.assertTrue(all(x['phase'] == 'pilot' for x in slots[:6]))
        for i in range(24):
            block = slots[6 + 3*i:9 + 3*i]
            self.assertEqual({'J1', 'J2', 'J3'}, {x['journey'] for x in block})
            self.assertEqual({i + 1}, {x['block'] for x in block})

    def test_guard_full_duration_at_launch_remaining_duration_during_run(self):
        now = datetime(2026, 10, 3, tzinfo=timezone.utc)
        c = calendar(now, '2026-10-01')
        start = datetime.fromisoformat(c['latest_launch_utc'])
        calendar_guard(c, start)
        calendar_guard(c, start + timedelta(hours=95), started=start)
        for at, began in ((start + timedelta(seconds=1), None),
                          (start + timedelta(hours=96), start)):
            with self.assertRaises(Exception): calendar_guard(c, at, started=began)
        with self.assertRaises(Exception): calendar(now, '2026-09-26')

    def test_headline_21_each_j3_mandatory_void_scoped_and_pilots_excluded(self):
        rows = [{**x, 'passed': x['number'] <= 21, 'first_try_passed': False}
                for x in schedule('12' * 32)['slots']]
        result = analysis(rows)
        self.assertTrue(result['headline_supported'])
        self.assertAlmostEqual(.875, result['journeys']['J3']['final_rate'])
        self.assertFalse(analysis(rows[:-1])['headline_supported'])
        row = next(x for x in rows if x['id'] == 'j3-cohort-21')
        row['passed'] = False
        self.assertFalse(analysis(rows)['headline_supported'])
        value = analysis(rows, void_journeys=('J3',))
        self.assertIsNone(value['journeys']['J3']['final_rate'])
        self.assertEqual(.875, value['journeys']['J1']['final_rate'])
        self.assertIsNone(value['combined']['rate'])
        with self.assertRaises(Exception): analysis(rows + [rows[0]])


if __name__ == '__main__': unittest.main()
