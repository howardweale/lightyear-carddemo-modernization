"""Qualification needs exact native inputs, but has no builder to isolate."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from lightyear_calibration.contracts import canonical, seal, CalibrationError
from lightyear_calibration.journey_order import file_hash
from tools.ms94_b06_executable import window
from tools.ms94_b06_qualification_plan import convert


class ConversionTests(unittest.TestCase):
    def test_missing_snapshot_cannot_promote_draft(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(CalibrationError):
                convert(Path(d), seal({'journey': 'J1'}), 'missing', '', '')

    def test_conversion_ignores_builder_probe_but_binds_native_inputs(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            cal = seal({'period_start_utc': '2026-10-01T00:00:00Z',
                        'period_end_exclusive_utc': '2026-11-01T00:00:00Z',
                        'maximum_seconds': 345600, 'scenario_date': '2026-10-01',
                        'frozen_at_utc': '2026-10-05T00:00:00Z'})
            start, end = '2026-10-18T00:00:00Z', '2026-10-19T00:00:00Z'
            images = {'application': 'a', 'oracle': 'o', 'postgresql': 'p'}
            plan = seal({'journey': 'J1', 'slot_id': 'j1-001', 'execution_admission_version': 3,
                         'docker_run_window': window(cal, start, end), 'calendar': cal,
                         'local': {'runner_image': 'a'}, 'declaration': {'environment': {'engines': {
                             k: {'image_digest': images[k]} for k in ('oracle', 'postgresql')}}},
                         'harness_sha256': 'source', 'control': 'retained-reference', 'expected': {'status': 'passed'}})
            name = 'journey-' + 'a'*32 + '/plan.json'
            (root / name).parent.mkdir()
            (root / name).write_bytes(canonical(plan))
            manifest = seal({'files_sha256': {name: file_hash(root / name)},
                             'slot_plans_sha256': {name: plan['content_sha256']}})
            (root / 'b06-executable-snapshot.json').write_bytes(canonical(manifest))
            body = {'journey': 'J1', 'model_calls': 0, 'measurement_authorized': False,
                    'slot_count': 1, 'images': images, 'schedule': [{'id': 'j1-001',
                    'source': {'sha256': 'source'}, 'control': plan['control'], 'expected': plan['expected']}]}
            # Only native private-input checking is mocked; snapshot hashing and
            # slot/source/image/calendar validation use real files and code.
            with patch('tools.ms94_b06_qualification_plan.verify_inputs') as inputs, patch(
                    'tools.ms94_b06_os_probe.admit', side_effect=AssertionError('no builder')):
                result = convert(root, seal(body), manifest['content_sha256'], start, end,tower_public_key_sha256='a'*64)
                inputs.assert_called_once()
                self.assertFalse(result['builder_present'])
                self.assertFalse(result['docker_authorized'])
                self.assertNotIn('os_probe_sha256', result)
                for field, value in [('model_calls', 1), ('measurement_authorized', True)]:
                    with self.assertRaisesRegex(ValueError, 'qualification-only-no-builder'):
                        convert(root, seal({**body, field: value}), manifest['content_sha256'], start, end,tower_public_key_sha256='a'*64)
                changed = {**body, 'images': {**images, 'oracle': 'other'}}
                with self.assertRaisesRegex(ValueError, 'qualification-image-binding'):
                    convert(root, seal(changed), manifest['content_sha256'], start, end,tower_public_key_sha256='a'*64)
            (root / name).write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, 'bound-file-changed'):
                convert(root, seal(body), manifest['content_sha256'], start, end,tower_public_key_sha256='a'*64)



    def test_five_path_census_is_explicit_and_never_qualification_credit(self):
        paths = [('J1','retained-reference'), ('J1','duplicate-invoice-line'),
                 ('J1','invoice-null-dereference'), ('J2','retained-reference'),
                 ('J3','retained-reference')]
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            cal = seal({'period_start_utc':'2026-10-01T00:00:00Z',
                        'period_end_exclusive_utc':'2026-11-01T00:00:00Z',
                        'maximum_seconds':39600, 'scenario_date':'2026-10-01',
                        'frozen_at_utc':'2026-10-09T01:00:00Z'})
            start, end = '2026-10-09T03:00:00Z', '2026-10-09T14:00:00Z'
            images = {'application':'a', 'oracle':'o', 'postgresql':'p'}
            plans, files, schedule = {}, {}, []
            for i,(journey,control) in enumerate(paths):
                slot = {'id':f'census-{i}', 'journey':journey, 'control':control,
                        'source':{'sha256':f'source-{i}'}, 'expected':{'status':'passed'}}
                schedule.append(slot)
                plan = seal({'journey':journey, 'slot_id':slot['id'],
                    'execution_admission_version':3, 'calendar':cal,
                    'docker_run_window':window(cal,start,end),
                    'candidate_timeout_seconds':1800,
                    'local':{'runner_image':'a'}, 'declaration':{'policy':{'max_elapsed_seconds':7190,'max_model_calls':0},'environment':{'engines':{
                        k:{'image_digest':images[k]} for k in ('oracle','postgresql')}}},
                    'harness_sha256':slot['source']['sha256'], 'control':control,
                    'expected':slot['expected'], 'built_runtime':{},
                    'posting_observer':{'observer_binding_v2':{'policy':'observer-binding-v2'}}})
                name = f'journey-{i:032x}/plan.json'
                (root/name).parent.mkdir(); (root/name).write_bytes(canonical(plan))
                plans[name] = plan['content_sha256']; files[name] = file_hash(root/name)
            manifest = seal({'files_sha256':files,'slot_plans_sha256':plans})
            (root/'b06-executable-snapshot.json').write_bytes(canonical(manifest))
            body = {'journey':'multi', 'purpose':'five-path-provenance-census',
                    'qualification_credit':False, 'model_calls':0, 'measurement_authorized':False,
                    'slot_count':5, 'images':images, 'schedule':schedule}
            def run(value):
                return convert(root,seal(value),manifest['content_sha256'],start,end,
                               tower_public_key_sha256='a'*64)
            with patch('tools.ms94_b06_qualification_plan.verify_inputs'):
                result = run(body)
                self.assertEqual(result['journeys'],['J1','J2','J3'])
                self.assertFalse(result['qualification_credit'])
                self.assertEqual(result['slot_count'],5)
                self.assertFalse(result['docker_authorized'])
                for change in ({'qualification_credit':True}, {'purpose':'qualification'},
                               {'schedule':list(reversed(schedule))}):
                    with self.assertRaises(ValueError): run({**body,**change})
                wrong = [dict(x) for x in schedule]; wrong[-1]['journey']='J2'
                with self.assertRaisesRegex(ValueError,'census-five-path-schedule'):
                    run({**body,'schedule':wrong})
                # A correctly hashed snapshot with a swapped slot journey must fail.
                import json
                name = next(iter(plans)); plan=json.loads((root/name).read_text())
                plan.pop('content_sha256'); plan['journey']='J3'; plan=seal(plan)
                (root/name).write_bytes(canonical(plan)); plans[name]=plan['content_sha256']
                files[name]=file_hash(root/name)
                manifest=seal({'files_sha256':files,'slot_plans_sha256':plans})
                (root/'b06-executable-snapshot.json').write_bytes(canonical(manifest))
                with self.assertRaisesRegex(ValueError,'qualification-slot-binding'): run(body)

if __name__ == '__main__': unittest.main()
