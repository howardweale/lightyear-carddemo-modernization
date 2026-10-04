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
