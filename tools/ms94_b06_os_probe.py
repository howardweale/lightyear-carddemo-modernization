"""Signed OS denial evidence admission; failure reports cannot admit a builder."""
from pathlib import Path
from lightyear_calibration.contracts import read_json
from lightyear_calibration.journey_order import file_hash
from lightyear_control_tower.decisions import verify_envelope
from tools.ms94_b06_admission import check, bound_file


def admit(root, binding, public_key, transport):
    """Bind actual probe bytes, identity and tested policy to the future transport.

    Synthetic unit fixtures never qualify the native transport. Public policy
    excludes clocks, native execution, networking and model calls from this probe.
    """
    path = bound_file(root, binding['path'], binding['sha256'])
    record = read_json(path)
    check(verify_envelope(record, public_key), 'builder-probe-signature')
    if record.get('artifact_type') == 'ms94-b06-os-builder-denial/2':
        return admit_windows(root, record, transport)
    check(record['artifact_type'] == 'ms94-b06-os-builder-denial/1' and
          record['status'] == 'passed' and record['evidence_kind'] == 'actual-host-process',
          'builder-filesystem-denial-not-demonstrated')
    check(record['appcontainer_sid'] == transport['appcontainer_sid'] and
          record['policy_sha256'] == transport['policy_sha256'] and
          record['launcher_sha256'] == transport['launcher_sha256'] and
          record['runtime_sha256'] == transport['runtime_sha256'], 'builder-probe-transport-binding')
    check(record['capabilities'] == [] and record['inherited_handles'] is False and
          record['child_exit_code'] == 0 and record['token_is_appcontainer'] is True and
          record['denial_win32_error'] == 5 and record['positive_control_opened'] is True,
          'builder-probe-not-an-access-denial')
    target = bound_file(root, record['target']['path'], record['target']['sha256'])
    check(Path(record['target']['path']).parts[0] == 'tools' and target.is_file(), 'builder-probe-wrong-target')
    bound_file(root, transport['launcher_path'], transport['launcher_sha256'])
    check(file_hash(transport['runtime_path']) == transport['runtime_sha256'], 'builder-runtime-changed')
    return record


def is_access_denied(result):
    """Use Win32Exception.NativeErrorCode, never its generic E_FAIL HRESULT."""
    if result.get('opened') is not False or result.get('error') != 5:
        return False
    if result.get('exception_type') == 'System.ComponentModel.Win32Exception':
        return result.get('native_error') == 5
    return (result.get('exception_type') == 'System.UnauthorizedAccessException' and
            result.get('hresult') == -2147024891)  # HRESULT_FROM_WIN32(ERROR_ACCESS_DENIED)


def admit_windows(root, record, transport):
    """Dedicated local-account evidence, distinct from the failed AppContainer.

    Get-Content can report missing files with a managed ItemNotFound HRESULT;
    it must never be normalized to access denied. A Win32 exception must carry
    native code 5; UnauthorizedAccessException must carry HRESULT 0x80070005.
    """
    check(record['status'] == 'passed' and record['evidence_kind'] == 'actual-host-process' and
          record['method'] == transport['method'] == 'windows-local-account', 'builder-filesystem-denial-not-demonstrated')
    for name in ('account_sid','policy_sha256','launcher_sha256','runtime_sha256','child_script_sha256'):
        check(record[name] == transport[name], 'builder-probe-transport-binding')
    check(record['child_exit_code'] == 0 and record['identity_sid'] == record['account_sid'] and
          record['administrator'] is False and record['local_group_sids'] == ['S-1-5-32-545'] and
          'S-1-5-32-544' not in record['token_group_sids'] and
          record['positive_control_opened'] is True and record['missing_control']['opened'] is False and
          record['missing_control']['category'] == 'ObjectNotFound' and record['missing_control']['error'] != 5,
          'builder-probe-not-an-access-denial')
    check({t['role'] for t in record['targets']} == {'tools','private'} and len(record['targets']) == 2,
          'builder-probe-target-coverage')
    for target in record['targets']:
        bound_file(root, target['path'], target['sha256'])
        check(target['existed_before'] is True and is_access_denied(target), 'builder-probe-not-an-access-denial')
        if target['role'] == 'tools':
            check(Path(target['path']).parts[0] == 'tools', 'builder-probe-wrong-target')
        else:
            check(Path(target['path']).is_relative_to(Path(transport['private_directory'])), 'builder-probe-wrong-private-target')
    check(record['protected_directories'] == [str(Path(root).resolve()/'tools'),
                                             str((Path(root)/transport['private_directory']).resolve())],
          'builder-probe-root-differs')
    bound_file(root, transport['launcher_path'], transport['launcher_sha256'])
    bound_file(root, transport['child_script_path'], transport['child_script_sha256'])
    bound_file(root, transport['policy_path'], transport['policy_sha256'])
    if record.get('launch_method') == 'windows-runas-short-commands':
        check(record['command_factory_sha256'] == transport['command_factory_sha256'], 'builder-probe-command-binding')
        bound_file(root, transport['command_factory_path'], transport['command_factory_sha256'])
    check(file_hash(transport['runtime_path']) == transport['runtime_sha256'], 'builder-runtime-changed')
    return record
