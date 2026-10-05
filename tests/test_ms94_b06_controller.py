"""Controller core unit tests; real Tower authority/export tests are separate."""
import hashlib
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from lightyear_calibration.contracts import canonical, seal
from tools.ms94_b06_controller import ADMISSIONS, Controller
from tools.ms94_b06_design import LIMITS, TRIAL_LIMITS, calendar, schedule
from tests.test_ms94_b06_measurement_admission import builder_fixture


class BoundaryFixture:
    def __init__(self, plan):
        self.value = {'state':'ready', 'trials':[], 'calendar':plan['calendar'],
                      'bindings':{'plan':hashlib.sha256(canonical(plan)).hexdigest()}}
    def launch(self, *args):
        assert args[-1]() is True
        self.value['state'] = 'running'
    def guard(self, now): pass
    def start_trial(self, trial, now): self.value['active_trial'] = trial
    def record_usage(self, *args): pass
    def request_pause(self, *args): self.value['state'] = 'paused'
    def finish_and_review(self, row, *args):
        self.value['trials'].append(row)
        self.value['active_trial'] = None


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.now = datetime(2026,10,3,tzinfo=timezone.utc)
        self.tick = 100.0
        builder_spec, self.builder_context = builder_fixture(self.tmp.name)
        self.plan = seal({'builder_boundary': builder_spec, 'schedule':schedule('12'*32), 'calendar':calendar(self.now,'2026-10-01'),
                          'limits':LIMITS,'trial_limits':TRIAL_LIMITS})
        self.tower = BoundaryFixture(self.plan)
        self.c = Controller(Path(self.tmp.name)/'campaign',self.tower,self.plan,seal,monotonic=lambda:self.tick)
        self.admissions = {k:lambda:True for k in ADMISSIONS}
    def launch(self): self.c.launch(None,None,None,None,self.now,self.admissions, builder_context=self.builder_context)
    def pause(self):
        return self.c.provider_interruption(self.now,receipt_sha256='a'*64,review_root=None,artifacts=None)

    def test_admission_failure_leaves_no_started_and_can_be_corrected_before_launch(self):
        self.admissions['client'] = lambda:False
        with self.assertRaises(Exception): self.launch()
        self.assertFalse((self.c.directory/'started.json').exists())
        self.admissions['client'] = lambda:True
        self.launch()
        self.assertTrue((self.c.directory/'started.json').exists())
        with self.assertRaises(Exception): self.launch()

    def test_no_model_adapter_no_authority_shortcut(self):
        self.tower.value['bindings']['plan'] = 'b'*64
        with self.assertRaises(Exception):
            Controller(self.c.directory,self.tower,self.plan,seal,monotonic=lambda:0)

    def test_true_callbacks_cannot_skip_builder_probe(self):
        with self.assertRaisesRegex(ValueError, 'measurement-builder-probe-required'):
            self.c.launch(None,None,None,None,self.now,self.admissions)
        self.assertFalse((self.c.directory/'started.json').exists())
        (Path(self.tmp.name)/'probe.json').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'bound-file-changed'): self.launch()
        self.assertFalse((self.c.directory/'started.json').exists())

    def test_provider_retry_same_slot_preserves_budget_deadline_and_counts_campaignwide(self):
        self.launch(); active=self.c.start_next(self.now)
        self.c.charge(calls=1,now=self.now)
        for _ in range(3):
            self.assertTrue(self.pause())
            with self.assertRaises(Exception): self.c.start_next(self.now)
            with self.assertRaises(Exception): self.c.retry_provider(self.now)
            self.tower.value['state']='running'  # Simulates the separately tested signed Tower continue.
            retried=self.c.retry_provider(self.now)
            self.assertEqual(active['slot'],retried['slot'])
            self.assertEqual(active['deadline'],retried['deadline'])
            self.assertEqual(1,retried['calls'])
        self.assertFalse(self.pause())
        self.tower.value['state']='running'
        with self.assertRaises(Exception): self.c.retry_provider(self.now)
        self.assertEqual([],self.c.finished)
        self.assertTrue(all(x['verdict'] is None and not x['candidate_failure'] for x in self.c.interruptions))

    def test_after_evaluation_interruption_cannot_retry_or_become_candidate_failure(self):
        self.launch();self.c.start_next(self.now);self.c.mark_evaluated(self.now)
        self.assertFalse(self.pause())
        self.tower.value['state']='running'
        with self.assertRaises(Exception): self.c.retry_provider(self.now)

    def test_work_reserve_and_finalization_inclusive_deadline(self):
        self.launch();active=self.c.start_next(self.now)
        self.tick=active['work_deadline']
        with self.assertRaises(Exception): self.c.charge(calls=1,now=self.now)
        self.tick=active['deadline']
        row={k:active['slot'][k] for k in ('id','journey','phase')}
        row.update(state='passed',fingerprints=[],receipt_sha256='f'*64)
        with self.assertRaises(Exception): self.c.finish(row,self.now,review_root=None,artifacts=None)

    def test_per_trial_budget_not_reset_by_interruption(self):
        self.launch();self.c.start_next(self.now)
        self.c.charge(calls=5,compilations=3,now=self.now)
        with self.assertRaises(Exception):self.c.charge(calls=1,now=self.now)
        with self.assertRaises(Exception):self.c.charge(compilations=1,now=self.now)

    def test_slow_export_cannot_admit_another_slot_after_finalization_deadline(self):
        self.launch(); active = self.c.start_next(self.now)
        row = {k: active['slot'][k] for k in ('id','journey','phase')}
        row.update(state='passed', fingerprints=[], receipt_sha256='f'*64)
        original = self.tower.finish_and_review
        def slow_export(*args):
            original(*args)
            self.tick = active['deadline']
        self.tower.finish_and_review = slow_export
        with self.assertRaisesRegex(Exception, 'Finalization exceeded'):
            self.c.finish(row, self.now, review_root=None, artifacts=None)
        self.assertEqual([row], self.tower.value['trials'])
        self.assertEqual(0, self.c.next_index)
        with self.assertRaisesRegex(Exception, 'no next slot'):
            self.c.start_next(self.now)


if __name__ == '__main__': unittest.main()
