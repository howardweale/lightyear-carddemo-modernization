"""Real signed Tower decisions through the controller core; no native worker."""
import unittest
from datetime import datetime, timezone
from lightyear_calibration.contracts import canonical, seal
from lightyear_control_tower.b06 import B06TowerBoundary, StatusWriter, write_request, read_exports
from tests import test_b06_tower
from tools.ms94_b06_controller import Controller, ADMISSIONS
from tools.ms94_b06_design import schedule, calendar, LIMITS, TRIAL_LIMITS


class ControllerTowerTests(unittest.TestCase):
    def test_real_authority_pause_continue_wrong_pause_and_void(self):
        f = test_b06_tower.B06Tests('test_launch_requires_every_binding_and_admission_before_start')
        f.setUp()
        self.addCleanup(f.doCleanups)
        # Calendar is a fixed test fixture; no clock is altered.
        now = datetime(2026, 10, 3, tzinfo=timezone.utc)
        plan = seal({'schedule': schedule('34'*32), 'calendar': calendar(now, '2026-10-01'),
                     'limits': LIMITS, 'trial_limits': TRIAL_LIMITS})
        artifacts = {**f.artifacts, 'plan': canonical(plan)}
        item, bound = write_request(f.root, 'campaign-authorization', artifacts)
        bindings = {key: bound[key] for key in f.bindings}
        exports = f.engine/'controller-export'
        boundary = B06TowerBoundary(StatusWriter(exports, f.sign, f.public), bindings,
            {key: plan['calendar'][key] for key in f.calendar}, fixture=True)
        boundary.emit(now)
        controller = Controller(f.engine/'controller', boundary, plan, f.sign, monotonic=lambda: 100.0)
        proof = f.decide(item, 'authorized')
        head = proof['journal']['journal_head_sha256']
        admissions = {name: lambda: True for name in ADMISSIONS}
        controller.launch(proof, f.s.public_key, bound, head, now, admissions)
        review_artifacts = {key: artifacts[key] for key in ('campaign','plan','executable')}
        # J1 repeats in a distinct trial; J2/J3's identical fingerprint cannot pause J1.
        pause = None
        for index in range(4):
            active = controller.start_next(now)
            row = {key: active['slot'][key] for key in ('id','journey','phase')}
            row.update(state='failed', fingerprints=['a'*64, 'a'*64], receipt_sha256='b'*64)
            pause = controller.finish(row, now, review_root=f.root, artifacts=review_artifacts)
            self.assertEqual('paused' if index == 3 else 'running', boundary.value['state'])
        prior_rows = list(boundary.value['trials'])
        with self.assertRaises(Exception): controller.start_next(now)
        decision = f.decide(pause[0], 'continue')
        boundary.resolve(decision, f.s.public_key, decision['journal']['journal_head_sha256'], now)
        self.assertEqual(prior_rows, boundary.value['trials'])
        active = controller.start_next(now)
        self.assertEqual('j2-pilot-02', active['slot']['id'])
        row = {key: active['slot'][key] for key in ('id','journey','phase')}
        row.update(state='equipment-suspect', fingerprints=[], receipt_sha256='c'*64)
        pause = controller.finish(row, now, review_root=f.root, artifacts=review_artifacts)
        with self.assertRaisesRegex(ValueError, 'bound-hash'):
            boundary.resolve(decision, f.s.public_key, decision['journal']['journal_head_sha256'], now)
        self.assertEqual('paused', boundary.value['state'])
        decision = f.decide(pause[0], 'void')
        boundary.resolve(decision, f.s.public_key, decision['journal']['journal_head_sha256'], now)
        with self.assertRaises(Exception): controller.start_next(now)
        exported = read_exports(exports, f.public, 'ms94-b06', bindings)
        self.assertEqual('void', exported['state'])
        self.assertEqual(5, len(exported['trials']))
        self.assertEqual(prior_rows, exported['trials'][:4])


if __name__ == '__main__': unittest.main()
