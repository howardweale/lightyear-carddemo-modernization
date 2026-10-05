"""Pinned exec construction/probe admission. No prompt sender or model authority."""
import json
from pathlib import Path, PureWindowsPath
from lightyear_calibration.contracts import canonical, digest, read_json, seal
from lightyear_calibration.journey_order import file_hash
from lightyear_control_tower.decisions import verify_envelope
from tools.ms94_b06_admission import check, bound_file, sign_once

PATH = r'C:\Program Files\Lightyear\Codex\0.160.0\codex.exe'
SHA = '4b01d5920e6785614727443bbecf343f4dedbb7347052b72ba805aab6353ef01'
LAUNCHER = 'tools/ms94_b06_pinned_probe.ps1'
FILES = (LAUNCHER, 'tools/ms94_b06_pinned_exec.ps1', 'tools/b06-account-egress.cs',
         'tools/ms94_b06_codex_probe_child.ps1', 'tools/ms94_b06_pinned_transport.py')
ARGS = ('exec --ignore-user-config --disable shell_tool --disable apps --disable multi_agent '
        '--config web_search="disabled" --config approval_policy="never" '
        '--json --ephemeral --skip-git-repo-check --sandbox read-only -')


def plan(root, sid):
    """Bind the exact installed client and account without publishing the raw SID."""
    return seal({'artifact_type':'ms94-b06-pinned-transport-plan/1', 'version':'0.160.0',
        'codex_path':PATH,'codex_sha256':SHA,'account_sid_sha256':digest(sid),
        'exec_arguments':ARGS,'implementation_sha256':{p:file_hash(Path(root)/p) for p in FILES},
        'network_policy':'WFP ALE connect v4/v6: block this SID when app ID differs from pinned path',
        'smoke_additional_restriction':'block pinned Codex too; no external connection or credentials',
        'model_calls_authorized':False,'measurement_ready':False,
        'review':'operator review; not independent attestation'})


def validate(record, transport, process_binding):
    check(record.get('artifact_type')=='ms94-b06-pinned-transport-proof/1' and
          record.get('status')=='passed', 'pinned-transport-proof-not-passed')
    check(PureWindowsPath(transport['codex_path'])==PureWindowsPath(PATH) and
          record['codex_path']==PATH and record['codex_sha256']==transport['codex_sha256']==SHA and
          record['account_sid_sha256']==digest(transport['account_sid']), 'pinned-client-or-account-differs')
    check(record['process_probe_sha256']==process_binding['sha256'], 'pinned-process-proof-differs')
    e=record['exec']
    check(e['arguments']==ARGS and e['stdin_bytes']==e['stdout_bytes']==e['model_calls']==0 and
          e['prompt_sent'] is False and e['exit_code']==1 and e['missing_prompt_rejected'] is True and
          e['codex_path']==PATH and e['codex_sha256']==SHA and e['account_sid']==transport['account_sid'],
          'pinned-exec-not-zero-model-eof')
    check(record['wfp_verified'] is True and record['wfp_filters_removed'] is True and
          record['account_disabled'] is True and record['temporary_codex_block_removed'] is True,
          'pinned-network-probe-or-cleanup-failed')
    probes=record['network_probes']
    check(len(probes)==2 and {p['address'] for p in probes}=={'127.0.0.1','::1'} and all(
          p['error']==10013 and p['connected'] is False and p['host_positive_connected'] is True and
          p['identity_sid']==transport['account_sid'] for p in probes), 'pinned-other-program-egress-not-denied')


def admit(root, transport, key, process_binding):
    binding=transport.get('pinned_probe')
    check(isinstance(binding,dict), 'pinned-exec-proof-required')
    proof=read_json(bound_file(root,binding['path'],binding['sha256']))
    check(verify_envelope(proof,key), 'pinned-proof-signature')
    validate(proof,transport,process_binding)
    for name,sha in proof['implementation_sha256'].items(): bound_file(root,name,sha)
    check(set(proof['implementation_sha256'])==set(FILES), 'pinned-implementation-binding-incomplete')
    check(file_hash(Path(transport['codex_path']))==SHA, 'pinned-runtime-changed')
    check(transport['pinned_plan_sha256']==proof['plan_sha256'], 'pinned-plan-differs')
    return proof


def record(root, source, destination, signer):
    """Seal fresh actual observations only. No old proof is re-signed or amended."""
    from tools.ms94_b06_codex_probe_record import record as process_record
    root,source,destination=map(lambda p:Path(p).resolve(),(root,source,destination))
    load=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))
    host=load(source/'host.json'); cleanup=load(source/'cleanup.json')
    spec=plan(root,host['account_sid'])
    _,binding=process_record(root,source,destination,PATH,signer,launcher=LAUNCHER)
    body={'artifact_type':'ms94-b06-pinned-transport-proof/1','status':'passed',
        'codex_path':PATH,'codex_sha256':SHA,'account_sid_sha256':digest(host['account_sid']),
        'process_probe_sha256':binding['process_probe']['sha256'], 'plan_sha256':spec['content_sha256'],
        'exec':host['pinned_exec'],'wfp_verified':host['wfp_verified'],
        'network_probes':host['network_probes'], 'wfp_filters_removed':cleanup['wfp_filters_removed'],
        'account_disabled':cleanup['account_disabled'], 'temporary_codex_block_removed':cleanup['firewall_rule_removed'],
        'implementation_sha256':spec['implementation_sha256'],
        'raw_observation_sha256':{n:file_hash(source/n) for n in ('host.json','cleanup.json','exec.json','network.json','wfp-recovery.json')},
        'model_calls':0,'docker_runs':0,'measurement_ready':False,'review':spec['review']}
    validate(body,binding['transport'],binding['process_probe'])
    signed=sign_once(destination/'pinned-exec.json',body,signer)
    (destination/'pinned-plan.json').write_bytes(canonical(spec))
    binding['transport'].update(pinned_probe={'path':(destination/'pinned-exec.json').relative_to(root).as_posix(),
        'sha256':file_hash(destination/'pinned-exec.json')},pinned_plan_sha256=spec['content_sha256'])
    # Do not overwrite the process proof's original binding artifact.
    (destination/'pinned-binding.json').write_bytes(canonical(binding))
    admit(root,binding['transport'],signer.public,binding['process_probe'])
    return signed,binding,spec
