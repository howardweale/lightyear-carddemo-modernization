import copy
import json
import tempfile
import unittest
from pathlib import Path
from lightyear_calibration.contracts import canonical
from lightyear_calibration.journey_order import file_hash
from tests.test_ms94_a3_entry_v2 import test_signer
from tools.ms94_b06_os_probe import admit
from tools.ms94_b06_windows_probe_record import record as record_observation


class WindowsACLAdmissionTests(unittest.TestCase):
    def test_recorder_binds_observation_and_refuses_failed_or_changed_child(self):
        with tempfile.TemporaryDirectory() as directory:
            # Match the recorder's canonical paths (Windows CI temp may use RUNNER~1).
            root=Path(directory).resolve(); (root/'tools').mkdir(); (root/'private').mkdir()
            observed=root/'observed'; (observed/'public').mkdir(parents=True); (observed/'child-output').mkdir()
            launcher=root/'tools/ms94_b06_windows_acl_probe.ps1'
            target=root/'tools/target.py'; private=root/'private/control'; runtime=root/'powershell.exe'
            for file in (launcher,target,private,runtime,observed/'public/probe-child.ps1'):file.write_bytes(b'unit fixture')
            policy={'account_sid':'fixture','protected_directories':[str(root/'tools'),str(root/'private')],
                    'protected_targets':[str(target),str(private)]}
            (observed/'public/policy.json').write_text(json.dumps(policy),encoding='utf-8-sig')
            child={'identity_sid':'fixture','administrator':False,'group_sids':['S-1-5-32-545'],
                   'positive':{'opened':True},'missing':{'opened':False,'category':'ObjectNotFound','error':5377},
                   'denials':[{'opened':False,'error':5,'hresult':-2147024891,'exception_type':'System.UnauthorizedAccessException'} for _ in range(2)]}
            child_path=observed/'child-output/result.json'
            child_path.write_text(json.dumps(child),encoding='utf-8-sig')
            observation={'artifact_type':'ms94-b06-windows-acl-observation/1','status':'passed','child_exit_code':0,
                         'model_calls':0,'native_pairs':0,'account_sid':'fixture','local_group_sids':['S-1-5-32-545'],
                         'child':child,'acls':[{'path':p} for p in policy['protected_directories']],
                         'target_sha256':file_hash(target),'private_target_sha256':file_hash(private),
                         'target_existed_before':True,'private_target_existed_before':True,
                         'launcher_sha256':file_hash(launcher),'runtime_path':str(runtime),'runtime_sha256':file_hash(runtime),
                         'policy_sha256':file_hash(observed/'public/policy.json'),
                         'child_script_sha256':file_hash(observed/'public/probe-child.ps1'),
                         'started_utc':'fixture','ended_utc':'fixture'}
            (observed/'observation.json').write_text(json.dumps(observation),encoding='utf-8-sig')
            signer=test_signer()
            result,binding,transport=record_observation(root,observed,root/'recorded','private',signer)
            self.assertEqual(admit(root,binding,signer.public,transport),result)
            child_path.write_text(json.dumps({**child,'administrator':True}),encoding='utf-8-sig')
            with self.assertRaisesRegex(ValueError,'probe-child-observation-differs'):
                record_observation(root,observed,root/'changed','private',signer)
            self.assertFalse((root/'changed').exists())
            (observed/'failure.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'probe-has-failure-record'):
                record_observation(root,observed,root/'failed','private',signer)

    def test_real_error_five_existing_targets_limited_identity_and_positive_control_required(self):
        with tempfile.TemporaryDirectory() as directory:
            # Match the recorder's canonical paths (Windows CI temp may use RUNNER~1).
            root=Path(directory).resolve(); (root/'tools').mkdir(); (root/'private').mkdir()
            for name in ('tools/probe.ps1','tools/target.py','private/control','child.ps1','policy.json','powershell.exe'):
                (root/name).write_bytes(name.encode())
            transport={'method':'windows-local-account','account_sid':'S-1-fixture',
                       'private_directory':'private','runtime_path':str(root/'powershell.exe')}
            for key,name in [('launcher','tools/probe.ps1'),('child_script','child.ps1'),('policy','policy.json')]:
                transport[key+'_path']=name; transport[key+'_sha256']=file_hash(root/name)
            transport['runtime_sha256']=file_hash(root/'powershell.exe')
            record={'artifact_type':'ms94-b06-os-builder-denial/2','method':transport['method'],
                    'status':'passed','evidence_kind':'actual-host-process','account_sid':transport['account_sid'],
                    **{k:v for k,v in transport.items() if k.endswith('_sha256')},
                    'child_exit_code':0,'identity_sid':transport['account_sid'],'administrator':False,
                    'local_group_sids':['S-1-5-32-545'],'token_group_sids':['S-1-5-32-545'],
                    'positive_control_opened':True,'missing_control':{'opened':False,'category':'ObjectNotFound','error':5377},
                    'protected_directories':[str(root.resolve()/'tools'),str(root.resolve()/'private')],
                    'targets':[{'role':role,'path':name,'sha256':file_hash(root/name),'existed_before':True,
                                'opened':False,'error':5,'hresult':-2147024891,'exception_type':'System.UnauthorizedAccessException'}
                               for role,name in [('tools','tools/target.py'),('private','private/control')]]}
            signer=test_signer()
            def test(body):
                (root/'record.json').write_bytes(canonical(signer.sign(body)))
                return admit(root,{'path':'record.json','sha256':file_hash(root/'record.json')},signer.public,transport)
            test(record)
            # Synthetic v2 signature fixture through both measurement boundaries.
            # This tests integration, not an actual Windows denial or native run.
            from datetime import datetime, timezone
            from lightyear_calibration.contracts import digest, seal
            from tools.ms94_b06_measurement_admission import builder_gate
            from tools.ms94_b06_controller import ADMISSIONS, Controller
            from tools.ms94_b06_design import LIMITS, TRIAL_LIMITS, calendar, schedule
            from tests.test_ms94_b06_controller import BoundaryFixture
            context = {'root': root, 'public_key': signer.public, 'transport': transport}
            now = datetime(2026, 10, 5, tzinfo=timezone.utc)
            plan = seal({'builder_boundary': {
                'probe': {'path': 'record.json', 'sha256': file_hash(root/'record.json')},
                'transport_sha256': digest(transport)},
                'schedule': schedule('12'*32), 'calendar': calendar(now, '2026-10-01'),
                'limits': LIMITS, 'trial_limits': TRIAL_LIMITS})
            self.assertEqual(file_hash(root/'record.json'), builder_gate(plan, context)['probe_file_sha256'])
            controller = Controller(root/'campaign', BoundaryFixture(plan), plan, seal, monotonic=lambda: 100.)
            controller.launch(None, None, None, None, now, {k: lambda: True for k in ADMISSIONS},
                              builder_context=context)
            self.assertTrue((root/'campaign/started.json').exists())
            native=copy.deepcopy(record)
            for target in native['targets']:
                target.update(exception_type='System.ComponentModel.Win32Exception',
                              native_error=5,hresult=-2147467259)
            test(native)
            for value in (None,2,16389):
                bad=copy.deepcopy(native); bad['targets'][0]['native_error']=value
                with self.subTest(native_error=value),self.assertRaises(ValueError):test(bad)
            for key,value in [('positive_control_opened',False),('administrator',True),('identity_sid','other'),
                              ('local_group_sids',['S-1-5-32-544']),('evidence_kind','synthetic'),('child_exit_code',1)]:
                with self.subTest(key=key),self.assertRaises(ValueError):test({**record,key:value})
            for i in (0,1):
                for key,value in [('error',2),('hresult',-2147467259),('existed_before',False),('opened',True),('exception_type','System.IO.FileNotFoundException')]:
                    bad=copy.deepcopy(record); bad['targets'][i][key]=value
                    with self.subTest(target=i,key=key),self.assertRaises(ValueError):test(bad)
            bad=copy.deepcopy(record);bad['missing_control']['error']=5
            with self.assertRaises(ValueError):test(bad)
            (root/'policy.json').write_bytes(b'changed')
            with self.assertRaises(ValueError):test(record)


if __name__=='__main__':unittest.main()
