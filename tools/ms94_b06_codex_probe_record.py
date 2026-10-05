"""Seal observed Codex/Windows proof in place; raw observations stay local."""
import json
from pathlib import Path
from lightyear_calibration.contracts import canonical
from lightyear_calibration.journey_order import file_hash
from tools.ms94_b06_admission import check, sign_once
from tools.ms94_b06_os_probe import admit_windows, admit
from tools.ms94_b06_codex_transport import validate_process, admit_process

LAUNCHER = 'tools/ms94_b06_codex_account_probe.ps1'
PROTOCOL = 'tools/ms94_b06_codex_probe_child.ps1'


def record(root, source, destination, codex, signer, *, launcher=LAUNCHER):
    root, source, destination, codex = map(lambda p:Path(p).resolve(), (root,source,destination,codex))
    check(destination.is_relative_to(root) and not destination.exists(), 'codex-new-local-proof-directory-required')
    check(not (source/'failure.json').exists(), 'codex-failed-observation-preserved')
    load=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))
    host=load(source/'host.json'); child=load(source/'child-output/observation.json')
    cleanup=load(source/'cleanup.json'); policy=load(source/'public/policy.json')
    protocol=load(source/'child-output/protocol.json')
    check(host['artifact_type']=='ms94-b06-codex-host-observation/1' and
          child['artifact_type']=='ms94-b06-codex-process-observation/1' and
          host['child_exit_code']==host['model_calls']==host['docker_runs']==0 and
          host['account_sid']==child['account_sid']==policy['account_sid'] and
          host['local_group_sids']==['S-1-5-32-545'] and protocol['requests']==child['requests'],
          'codex-observation-binding')
    check(launcher in (LAUNCHER,'tools/ms94_b06_pinned_probe.ps1'), 'codex-probe-launcher-not-allowed')
    check(host['launcher_sha256']==file_hash(root/launcher) and
          file_hash(source/'public/child.ps1')==file_hash(root/PROTOCOL), 'codex-probe-code-changed')
    for name,sha in host['input_sha256'].items():
        check(file_hash(Path(name))==sha, 'codex-probe-input-changed')
    check(child['codex_sha256']==policy['codex_sha256']==file_hash(codex), 'codex-binary-changed')
    check(not (source/'child-output/codex-home/auth.json').exists(), 'codex-probe-auth-not-empty')
    reads=child['reads']; paths=list(map(lambda p:Path(p).resolve(),policy['read_targets']))
    check(len(paths)==4 and paths[2]==root/'tools/ms94_b06_builder_boundary.py' and
          paths[3].is_relative_to(root/'work/b06-admission-r4'), 'codex-target-scope')
    for i,request in enumerate(child['requests'][2:]):
        args=request['params']
        check(args['cwd']==str(source/'public') and args['command'][:4]==[
              policy['powershell'],'-NoProfile','-NonInteractive','-Command'] and
              '$p.read_targets['+str(i)+']' in args['command'][4] and
              args['sandboxPolicy']=={'type':'externalSandbox','networkAccess':'restricted'},
              'codex-request-scope')
    body={'artifact_type':'ms94-b06-codex-process-proof/1','status':'passed',
          'evidence_kind':'actual-host-process','account_sid':child['account_sid'],
          'codex_sha256':child['codex_sha256'],'codex_pid':child['codex_pid'],
          'reads':reads,'rpc_methods':[r['method'] for r in child['requests']],
          'model_calls':child['model_calls'],'prompt_sent':child['prompt_sent'],'exit_code':child['exit_code'],
          'account_disabled_after':cleanup['account_disabled'],'firewall_removed_after':cleanup['firewall_rule_removed'],
          'outbound_block_observed':host['firewall_block_observed']=='Block',
          'targets_sha256':{'tools':file_hash(paths[2]),'private':file_hash(paths[3])},
          'implementation_sha256':{name:file_hash(root/name) for name in (launcher,PROTOCOL,
               'tools/ms94_b06_builder_boundary.py','tools/ms94_b06_codex_transport.py')},
          'observation_hashes':{name:file_hash(source/name) for name in
               ('host.json','cleanup.json','public/policy.json','child-output/observation.json','child-output/protocol.json')},
          'measurement_transport_admitted':False,'review':'operator review; not independent attestation'}
    transport={'method':'windows-local-account','account_sid':child['account_sid'],
               'codex_path':str(codex),'codex_sha256':child['codex_sha256'],
               'runtime_path':policy['powershell'],'runtime_sha256':file_hash(Path(policy['powershell'])),
               'private_directory':paths[3].parent.relative_to(root).as_posix(),
               'launcher_path':launcher,'launcher_sha256':file_hash(root/launcher),
               'child_script_path':PROTOCOL,'child_script_sha256':file_hash(root/PROTOCOL),
               'policy_path':(destination/'policy.json').relative_to(root).as_posix(),
               'policy_sha256':file_hash(source/'public/policy.json')}
    validate_process(body,transport)
    denial={'artifact_type':'ms94-b06-os-builder-denial/2','method':'windows-local-account',
        'status':'passed','evidence_kind':'actual-host-process',
        **{k:v for k,v in transport.items() if k.endswith('_sha256') or k=='account_sid'},
        'identity_sid':child['account_sid'],'administrator':False,'local_group_sids':host['local_group_sids'],
        'token_group_sids':reads[0]['group_sids'],'child_exit_code':0,'positive_control_opened':reads[0]['opened'],
        'missing_control':reads[1],'protected_directories':[str(root/'tools'),str(paths[3].parent)],
        'targets':[{'role':role,'path':paths[i].relative_to(root).as_posix(),'sha256':file_hash(paths[i]),
                    'existed_before':True,**reads[i]} for i,role in ((2,'tools'),(3,'private'))]}
    destination.mkdir(parents=True,exist_ok=False)
    (destination/'policy.json').write_bytes((source/'public/policy.json').read_bytes())
    admit_windows(root,denial,transport)
    signed_denial=sign_once(destination/'denial.json',denial,signer)
    signed_process=sign_once(destination/'codex-process.json',body,signer)
    binding=lambda name:{'path':(destination/name).relative_to(root).as_posix(),'sha256':file_hash(destination/name)}
    admit(root,binding('denial.json'),signer.public,transport)
    admit_process(root,binding('codex-process.json'),signer.public,transport,signed_denial)
    result={'probe':binding('denial.json'),'process_probe':binding('codex-process.json'),'transport':transport}
    (destination/'transport-binding.json').write_bytes(canonical(result))
    return signed_process,result
