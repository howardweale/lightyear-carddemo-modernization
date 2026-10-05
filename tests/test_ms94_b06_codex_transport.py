"""Synthetic signatures test admission only; never a real process-proof claim."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from lightyear_calibration.contracts import canonical
from lightyear_calibration.journey_order import file_hash
from tests.test_ms94_a3_entry_v2 import test_signer
from tools.ms94_b06_codex_transport import validate_process
from tools.ms94_b06_builder_boundary import ARGUMENTS, admit_transport
from tools.ms94_tool_policy_v5 import capability_arguments


def fixture():
    reads=[]
    for i in range(4):
        reads.append({'identity_sid':'fixture','parent_sid':'fixture','parent_pid':100,
            'parent_name':'codex.exe','process_id':200+i,'administrator':False,'group_sids':['S-1-5-32-545'],
            'opened':i==0,'error':0 if i==0 else 5377 if i==1 else 5,
            'category':'ObjectNotFound' if i==1 else 'PermissionDenied',
            'exception_type':'System.UnauthorizedAccessException','hresult':-2147024891})
    return {'artifact_type':'ms94-b06-codex-process-proof/1','status':'passed','evidence_kind':'actual-host-process',
        'account_sid':'fixture','codex_sha256':'a'*64,'model_calls':0,'prompt_sent':False,'exit_code':0,
        'account_disabled_after':True,'firewall_removed_after':True,'outbound_block_observed':True,
        'rpc_methods':['initialize','initialized']+['command/exec']*4,'reads':reads,'codex_pid':100}


class CodexTransportTests(unittest.TestCase):
    def test_recorder_admits_actual_record_shapes_and_preserves_failed_observation(self):
        from tools.ms94_b06_codex_probe_record import record, LAUNCHER, PROTOCOL
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();source=root/'observed';public=source/'public';public.mkdir(parents=True)
            output=source/'child-output';output.mkdir();(root/'tools').mkdir()
            private=root/'work/b06-admission-r4/control.txt';private.parent.mkdir(parents=True)
            target=root/'tools/ms94_b06_builder_boundary.py'
            for p in (root/LAUNCHER,root/PROTOCOL,root/'tools/ms94_b06_codex_transport.py',
                      target,private,root/'powershell.exe',root/'codex.exe'):
                p.write_bytes(b'unit fixture only')
            (public/'codex.exe').write_bytes((root/'codex.exe').read_bytes())
            (public/'child.ps1').write_bytes((root/PROTOCOL).read_bytes())
            def write(p,obj):p.write_text(json.dumps(obj),encoding='utf-8-sig')
            policy={'account_sid':'fixture','codex_sha256':file_hash(root/'codex.exe'),
                    'powershell':str(root/'powershell.exe'),'results_directory':str(output),
                    'read_targets':list(map(str,(public/'allowed.txt',public/'missing.txt',target,private)))}
            write(public/'policy.json',policy)
            requests=[{'method':'initialize'},{'method':'initialized'}]+[
                {'method':'command/exec','params':{'cwd':str(public),'command':[
                    policy['powershell'],'-NoProfile','-NonInteractive','-Command',f'$p.read_targets[{i}]'],
                    'sandboxPolicy':{'type':'externalSandbox','networkAccess':'restricted'}}} for i in range(4)]
            body=fixture()
            child={'artifact_type':'ms94-b06-codex-process-observation/1','account_sid':'fixture',
                   'requests':requests,'reads':body['reads'],'model_calls':0,'prompt_sent':False,
                   'exit_code':0,'codex_pid':100,'codex_sha256':policy['codex_sha256']}
            write(output/'observation.json',child);write(output/'protocol.json',{'requests':requests})
            write(source/'cleanup.json',{'account_disabled':True,'firewall_rule_removed':True})
            write(source/'host.json',{'artifact_type':'ms94-b06-codex-host-observation/1','account_sid':'fixture',
                'child_exit_code':0,'model_calls':0,'docker_runs':0,'local_group_sids':['S-1-5-32-545'],
                'launcher_sha256':file_hash(root/LAUNCHER),'firewall_block_observed':'Block',
                'input_sha256':{str(p):file_hash(p) for p in (target,private,public/'child.ps1',public/'policy.json')}})
            signer=test_signer()
            proof,binding=record(root,source,root/'proof',root/'codex.exe',signer)
            self.assertEqual('passed',proof['status'])
            with self.assertRaisesRegex(ValueError,'pinned-exec-proof-required'):
                admit_transport(capability_arguments(),ARGUMENTS,[],root=root,
                    probe_binding=binding['probe'],public_key=signer.public,transport=binding['transport'],
                    process_probe_binding=binding['process_probe'])
            write(source/'failure.json',{'status':'failed'})
            with self.assertRaisesRegex(ValueError,'failed-observation-preserved'):
                record(root,source,root/'failure-proof',root/'codex.exe',signer)
            self.assertFalse((root/'failure-proof').exists())

    def test_wrong_sid_non_descendant_models_missing_positive_and_fake_denials_fail(self):
        record=fixture(); transport={'method':'windows-local-account','account_sid':'fixture','codex_sha256':'a'*64}
        validate_process(record,transport)
        for field,value in [('account_sid','other'),('model_calls',1),('prompt_sent',True),('exit_code',1),
                            ('outbound_block_observed',False),('rpc_methods',['initialize','turn/start'])]:
            with self.subTest(field=field),self.assertRaises(ValueError):validate_process({**record,field:value},transport)
        for i,field,value in [(0,'opened',False),(1,'error',5),(2,'error',2),(2,'parent_pid',999),
                              (3,'identity_sid','other'),(3,'hresult',-2147467259),(3,'administrator',True)]:
            bad=copy.deepcopy(record);bad['reads'][i][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):validate_process(bad,transport)

    def test_admit_transport_requires_both_proofs_bound_to_same_sid_binary_and_targets(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'codex.exe').write_bytes(b'not executable fixture')
            signer=test_signer();body=fixture();body['codex_sha256']=file_hash(root/'codex.exe')
            body.update(targets_sha256={'tools':'b'*64,'private':'c'*64},implementation_sha256={})
            transport={'method':'windows-local-account','account_sid':'fixture',
                       'codex_sha256':body['codex_sha256'],'codex_path':str(root/'codex.exe')}
            os_record={'method':'windows-local-account','account_sid':'fixture',
                       'targets':[{'role':r,'sha256':s} for r,s in body['targets_sha256'].items()]}
            def seal_process(value):
                (root/'process.json').write_bytes(canonical(signer.sign(value)))
                return {'path':'process.json','sha256':file_hash(root/'process.json')}
            def admit(binding):
                return admit_transport(capability_arguments(),ARGUMENTS,[],root=root,probe_binding={},
                    public_key=signer.public,transport=transport,process_probe_binding=binding)
            with patch('tools.ms94_b06_os_probe.admit',return_value=os_record), \
                 patch('tools.ms94_b06_pinned_transport.admit'):
                with self.assertRaisesRegex(ValueError,'proof-required'):admit(None)
                self.assertTrue(admit(seal_process(body)))
                for field,value in [('account_sid','other'),('targets_sha256',{'tools':'d'*64,'private':'c'*64})]:
                    with self.subTest(field=field),self.assertRaises(ValueError):admit(seal_process({**body,field:value}))
                binding=seal_process(body);(root/'codex.exe').write_bytes(b'changed')
                with self.assertRaisesRegex(ValueError,'runtime-changed'):admit(binding)


if __name__=='__main__':unittest.main()
