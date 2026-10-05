"""Admission of the dedicated-account Codex process proof; no launch or model API."""
from pathlib import Path
from lightyear_calibration.contracts import read_json
from lightyear_calibration.journey_order import file_hash
from lightyear_control_tower.decisions import verify_envelope
from tools.ms94_b06_admission import bound_file, check
from tools.ms94_b06_os_probe import is_access_denied


def validate_process(record, transport):
    check(record['artifact_type'] == 'ms94-b06-codex-process-proof/1' and
          record['status'] == 'passed' and record['evidence_kind'] == 'actual-host-process',
          'codex-process-proof-not-passed')
    check(transport['method'] == 'windows-local-account' and
          record['account_sid'] == transport['account_sid'] and
          record['codex_sha256'] == transport['codex_sha256'], 'codex-account-or-binary-differs')
    check(record['model_calls'] == 0 and record['prompt_sent'] is False and
          record['exit_code'] == 0 and record['account_disabled_after'] is True and
          record['firewall_removed_after'] is True and record['outbound_block_observed'] is True,
          'codex-process-probe-incomplete')
    check(record['rpc_methods'] == ['initialize','initialized']+['command/exec']*4,
          'codex-probe-nonzero-model-protocol')
    reads = record['reads']
    check(len(reads) == 4 and all(r['identity_sid'] == record['account_sid'] and
          r['parent_sid'] == record['account_sid'] and r['parent_pid'] == record['codex_pid'] and
          r['parent_name'] == 'codex.exe' and type(r['process_id']) is int and
          r['administrator'] is False and 'S-1-5-32-544' not in r['group_sids'] and
          r['process_id'] != record['codex_pid'] for r in reads), 'codex-read-outside-process-tree')
    check(reads[0]['opened'] is True and reads[1]['opened'] is False and
          reads[1]['category'] == 'ObjectNotFound' and reads[1]['error'] != 5 and
          all(is_access_denied(r) for r in reads[2:]), 'codex-read-not-access-denied')


def admit_process(root, binding, key, transport, os_probe):
    check(isinstance(binding, dict), 'codex-process-proof-required')
    record = read_json(bound_file(root, binding['path'], binding['sha256']))
    check(verify_envelope(record, key), 'codex-process-proof-signature')
    validate_process(record, transport)
    check(os_probe['account_sid'] == record['account_sid'] and
          record['targets_sha256'] == {r['role']:r['sha256'] for r in os_probe['targets']},
          'codex-process-targets-differ')
    check(file_hash(Path(transport['codex_path'])) == record['codex_sha256'], 'codex-runtime-changed')
    for name, sha in record['implementation_sha256'].items(): bound_file(root, name, sha)
    return record
