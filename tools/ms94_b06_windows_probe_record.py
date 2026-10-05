"""Seal observed built-in Windows probe output; never launch or change an ACL.

Signing is operator review. Unit fixtures do not constitute host qualification.
Raw observations stay local; a public summary may reference only their hashes.
"""
import json
from pathlib import Path
from lightyear_calibration.contracts import canonical
from lightyear_calibration.journey_order import file_hash
from tools.ms94_b06_admission import check, sign_once
from tools.ms94_b06_os_probe import admit


def record(root, observation_directory, destination, private_directory, signer):
    root, source, destination = (Path(p).resolve() for p in (root, observation_directory, destination))
    check(destination.is_relative_to(root) and not destination.exists(), 'probe-record-destination')
    check(not (source/'failure.json').exists(), 'probe-has-failure-record')
    load = lambda p: json.loads(p.read_text(encoding='utf-8-sig'))
    observation = load(source/'observation.json'); policy = load(source/'public/policy.json')
    short_commands = observation.get('launch_method') == 'windows-runas-short-commands'
    child_name = 'probe-commands.json' if short_commands else 'probe-child.ps1'
    check(observation['artifact_type'] == 'ms94-b06-windows-acl-observation/1' and
          observation['status'] == 'passed' and observation['child_exit_code'] == 0 and
          observation['model_calls'] == observation['native_pairs'] == 0, 'probe-not-passed')
    launcher='tools/ms94_b06_windows_acl_probe.ps1'
    check(file_hash(root/launcher) == observation['launcher_sha256'], 'probe-launcher-changed')
    check(file_hash(source/'public/policy.json') == observation['policy_sha256'] and
          file_hash(source/'public'/child_name) == observation['child_script_sha256'], 'probe-input-changed')
    child = load(source/'child-output/result.json')
    check(child == observation['child'] and policy['account_sid'] == observation['account_sid'],
          'probe-child-observation-differs')
    if short_commands:
        commands=load(source/'public'/child_name)
        launches=load(source/'launch-results.json')
        check(len(commands)==len(launches)==5 and launches==observation['launches'] and
              all(row['index']==i and row['exit_code']==0 and 0<row['command_characters']<=1024
                  for i,row in enumerate(launches)), 'probe-short-launches-not-complete')
        identity=load(source/'child-output/identity.json')
        check(all(child[k]==identity[k] for k in ('identity_sid','identity_name','administrator','group_sids')),
              'probe-identity-result-differs')
        for i in range(4):
            value=load(source/'child-output'/f'read-{i}.json')
            check(value==(child['denials'][i] if i<2 else child['positive' if i==2 else 'missing']) and
                  value['identity_sid']==identity['identity_sid'] and value['administrator'] is False,
                  'probe-read-identity-differs')
    protected=[str(root/'tools'), str((root/private_directory).resolve())]
    check(policy['protected_directories'] == protected and
          [a['path'] for a in observation['acls'][:2]] == protected,
          'probe-protected-directories-differ')
    targets=[]
    for i,role in enumerate(('tools','private')):
        path=Path(policy['protected_targets'][i]).resolve()
        check(path.is_relative_to(Path(protected[i])), 'probe-target-outside-denied-directory')
        sha=observation['target_sha256' if i==0 else 'private_target_sha256']
        check(path.is_file() and file_hash(path)==sha, 'probe-target-changed')
        targets.append({'role':role,'path':path.relative_to(root).as_posix(),'sha256':sha,
                        'existed_before':observation['target_existed_before' if i==0 else 'private_target_existed_before'],
                        **child['denials'][i]})
    destination.mkdir(parents=True,exist_ok=False)
    for name in ('policy.json',child_name):
        with (destination/name).open('xb') as output:output.write((source/'public'/name).read_bytes())
    transport={'method':'windows-local-account','account_sid':observation['account_sid'],
               'private_directory':private_directory,'launcher_path':launcher,
               'launcher_sha256':observation['launcher_sha256'],'runtime_path':observation['runtime_path'],
               'runtime_sha256':observation['runtime_sha256'],
               'policy_path':(destination/'policy.json').relative_to(root).as_posix(),
               'policy_sha256':observation['policy_sha256'],
               'child_script_path':(destination/child_name).relative_to(root).as_posix(),
               'child_script_sha256':observation['child_script_sha256']}
    body={'artifact_type':'ms94-b06-os-builder-denial/2','method':'windows-local-account',
          'evidence_kind':'actual-host-process','status':'passed',
          **{k:v for k,v in transport.items() if k.endswith('_sha256') or k=='account_sid'},
          'identity_sid':child['identity_sid'],'administrator':child['administrator'],
          'token_group_sids':child['group_sids'],'local_group_sids':observation['local_group_sids'],
          'child_exit_code':observation['child_exit_code'],'positive_control_opened':child['positive']['opened'],
          'missing_control':child['missing'],'targets':targets,'protected_directories':protected,
          'observation_sha256':file_hash(source/'observation.json'),
          'child_result_sha256':file_hash(source/'child-output/result.json'),
          'started_utc':observation['started_utc'],'ended_utc':observation['ended_utc'],
          'model_calls':0,'native_pairs':0,'review':'operator review; not independent attestation'}
    if short_commands:
        factory='tools/ms94_b06_windows_probe_commands.ps1'
        check(file_hash(root/factory)==observation['command_factory_sha256'], 'probe-command-factory-changed')
        transport.update(command_factory_path=factory,command_factory_sha256=observation['command_factory_sha256'])
        body.update(launch_method='windows-runas-short-commands',command_factory_sha256=observation['command_factory_sha256'],
                    launch_results_sha256=file_hash(source/'launch-results.json'),
                    read_results_sha256={f'read-{i}.json':file_hash(source/'child-output'/f'read-{i}.json') for i in range(4)})
    # Validate all evidence before signing a passed record.
    from tools.ms94_b06_os_probe import admit_windows
    admit_windows(root,body,transport)
    result=sign_once(destination/'denial.json',body,signer)
    binding={'path':(destination/'denial.json').relative_to(root).as_posix(),
             'sha256':file_hash(destination/'denial.json')}
    admit(root,binding,signer.public,transport)
    with (destination/'transport-binding.json').open('xb') as output:
        output.write(canonical({'probe':binding,'transport':transport}))
    return result, binding, transport
