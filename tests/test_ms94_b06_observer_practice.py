"""A single native practice is explicit and cannot confer census/qualification credit."""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from lightyear_calibration.contracts import canonical, seal
from lightyear_calibration.journey_order import file_hash
from tools.ms94_b06_executable import window
from tools.ms94_b06_qualification_plan import convert
from tools.ms94_b06_group_decision import request


class PracticeTests(unittest.TestCase):
    def test_diagnostic_request_preserves_strict_scope(self):
        scope=dict(purpose='capture-refusal-context-only',qualification_credit=False,measurement_credit=False,
                   stop_at_first_anomaly=True,degradation_mode=False,automatic_retry=False,
                   minimum_full_plan_review_lead_seconds=14400)
        body=dict(purpose='observer-native-practice',journey='J1',slot_count=1,qualification_credit=False,
                  model_calls=0,measurement_authorized=False,snapshot_sha256='a'*64,docker_run_window={},diagnostic_scope=scope)
        good,_,_=request(seal(body),'b'*40)
        self.assertIn('solely to capture',good['summary'])
        self.assertNotIn('corrected external observer',good['summary'])
        for field,value in [('qualification_credit',True),('measurement_credit',True),('stop_at_first_anomaly',False),
                            ('degradation_mode',True),('automatic_retry',True),('minimum_full_plan_review_lead_seconds',0),
                            ('purpose','qualification')]:
            changed={**body,'diagnostic_scope':{**scope,field:value}}
            with self.subTest(field=field),self.assertRaisesRegex(ValueError,'diagnostic-capture-only'):
                request(seal(changed),'b'*40)

    def test_exact_one_pair_conversion_and_tower_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); start,end='2026-10-09T20:00:00Z','2026-10-09T23:00:00Z'
            cal=seal(dict(period_start_utc='2026-10-01T00:00:00Z',period_end_exclusive_utc='2026-11-01T00:00:00Z',
                maximum_seconds=39600,scenario_date='2026-10-01',frozen_at_utc='2026-10-09T19:00:00Z'))
            images=dict(application='a',oracle='o',postgresql='p')
            slot=dict(id='practice-001',control='retained-reference',source={'sha256':'source'},
                expected=dict(status='passed',equipment_suspect=False,diagnostics=[]))
            plan=seal(dict(journey='J1',slot_id=slot['id'],execution_admission_version=3,calendar=cal,
                docker_run_window=window(cal,start,end),local={'runner_image':'a'},
                declaration={'policy':{'max_elapsed_seconds':7190,'max_model_calls':0},'environment':{'engines':{
                    k:{'image_digest':images[k]} for k in ('oracle','postgresql')}}},
                candidate_timeout_seconds=1800,built_runtime={},
                posting_observer={'observer_binding_v2':{'policy':'observer-binding-v2'}},
                harness_sha256='source',control=slot['control'],expected=slot['expected']))
            name='journey-'+'1'*32+'/plan.json';(root/name).parent.mkdir();(root/name).write_bytes(canonical(plan))
            manifest=seal(dict(files_sha256={name:file_hash(root/name)},slot_plans_sha256={name:plan['content_sha256']}))
            (root/'b06-executable-snapshot.json').write_bytes(canonical(manifest))
            body=dict(journey='J1',purpose='observer-native-practice',qualification_credit=False,model_calls=0,
                measurement_authorized=False,slot_count=1,images=images,schedule=[slot])
            def run(b):return convert(root,seal(b),manifest['content_sha256'],start,end,tower_public_key_sha256='a'*64)
            with patch('tools.ms94_b06_qualification_plan.verify_inputs'):
                group=run(body)
                self.assertEqual(group['purpose'],'observer-native-practice');self.assertFalse(group['qualification_credit'])
                self.assertFalse(group['docker_authorized']);self.assertFalse(group['measurement_authorized'])
                req,_,_=request(group,'b'*40);self.assertIn('one fresh',req['summary']);self.assertIn('No retries',req['summary'])
                for change in ('journey','credit','control','outcome','count'):
                    bad=copy.deepcopy(body)
                    if change=='journey':bad['journey']='J2'
                    elif change=='credit':bad['qualification_credit']=True
                    elif change=='control':bad['schedule'][0]['control']='mutant'
                    elif change=='outcome':bad['schedule'][0]['expected']['status']='equipment-failure'
                    else:bad['slot_count']=2;bad['schedule'].append({**slot,'id':'practice-002'})
                    with self.subTest(change=change),self.assertRaises(ValueError):run(bad)
