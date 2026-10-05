"""Control plumbing over synthetic fixtures; no native qualification credit."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from lightyear_calibration.contracts import canonical, seal
from lightyear_calibration.journey_order import file_hash
from tests.test_ms94_a3_entry_v2 import test_signer
from tools.ms94_b06_qualification_controls import (BOUNDARIES, DB_MODULE, projection, rejection,
    native_mutation, validate_plan)


class QualificationControlTests(unittest.TestCase):
    def test_each_boundary_rejects_for_exact_reason_and_preserves_original(self):
        samples = [{'stage': stage, 'host_before_utc': '2026-10-05T12:00:00Z',
                    'host_after_utc': '2026-10-05T12:00:00Z', 'monotonic': n, 'value': stage}
                   for n, stage in enumerate(('before','after'))]
        runtime = [{'container': str(n), 'image': 'image', 'clock_manipulation_environment': False,
                    'privileged': False, 'sys_time_capability': False} for n in range(3)]
        clock = {'lanes': {l: {'queries': deepcopy(samples)} for l in ('oracle','postgresql')}, 'runtime': runtime}
        executions = {l: {'native_clock_before': {'value': 'before'}, 'native_clock_after': {'value': 'after'},
                         'content_sha256': l} for l in ('oracle','postgresql')}
        plan = {'evidence_contract': {'clock_stages': ['before','after'], 'runtime': {
            str(n): {'container':str(n),'image':'image'} for n in range(3)}}}
        original = canonical(clock)
        rejection(plan, clock, executions)
        for control, reason in BOUNDARIES.items():
            with self.subTest(control=control), self.assertRaisesRegex(ValueError, '^'+reason+'$'):
                rejection(plan, projection(clock, control), executions)
            self.assertEqual(canonical(clock), original)

    def test_native_mutation_requires_exact_recipe_and_successful_execution(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); path=root/DB_MODULE; path.parent.mkdir(parents=True); path.write_bytes(b'fixture module')
            plan={'journey':'J1','slot_kind':'native-mutator','control':'wrong-quantity','fault':'wrong-quantity',
                  'model_calls':0,'qualification_only':True,'implementation_sha256':{DB_MODULE:file_hash(path)},
                  'fault_recipe':seal({'fault':'wrong-quantity','unchanged_J1_mutator':True,
                                      'module':DB_MODULE,'module_sha256':file_hash(path)})}
            runner=SimpleNamespace(root=root,plan=plan,runner='owned-fixture',password='synthetic')
            signer=test_signer()
            with patch('lightyear_calibration.journey_runtime.docker') as docker:
                with self.assertRaisesRegex(ValueError,'mutation-reference-did-not-complete'):
                    native_mutation(runner,'oracle',{'exit_code':1},root,signer)
                docker.assert_not_called()
                docker.return_value.stdout=canonical(seal({'lane':'oracle','fault':'wrong-quantity',
                    'committed':True,'affected_rows':1,'qualification_only':True}))
                record=native_mutation(runner,'oracle',{'exit_code':0},root,signer)
                self.assertEqual(record['affected_rows'],1)
                self.assertEqual(docker.call_args.args[:4],('exec','-i','owned-fixture','python'))
                with self.assertRaises(ValueError): native_mutation(runner,'oracle',{'exit_code':0},root,signer)
                self.assertEqual(docker.call_count,1)
            for key,value in [('journey','J2'),('fault','other'),('implementation_sha256',{})]:
                with self.assertRaises(ValueError): validate_plan({**plan,key:value})


if __name__ == '__main__': unittest.main()
