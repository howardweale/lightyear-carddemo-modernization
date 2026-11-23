"""Create private H1 control files. Howard operates this terminal; no H1 mode is invoked."""
from datetime import datetime, timedelta, timezone
import getpass
import os
from pathlib import Path
import secrets
import sys
import warnings

from tools import intcalc_private_reference_host as h

GROUPS = {
    'C01': 'accounts_distinct private_account_standard private_account_dedicated fresh_tokens_checked membership_resolution_complete',
    'C02': 'codex_account_standard codex_outside_docker_users membership_resolution_complete',
    'C03': 'per_account_wsl2 private_distro_registration_join private_distro_absent_from_codex_registration backing_storage_acl_isolated backing_storage_local_no_sync_backup',
    'C04': 'native_linux_amd64 endpoint_local_unix engine_process_socket_distro_join desktop_engine_rejected endpoint_overrides_absent',
    'C05': 'private_root_native_distro_fs private_root_owner_only private_root_no_symlink_escape local_no_sync_backup_attested',
    'C06': 'codex_stopped_preflight process_visibility_complete no_codex_background_or_autostart operator_attends_full_window',
}
MODES = ('INSPECT', 'QUALIFY_PUBLIC')


def utc():
    return datetime.now(timezone.utc)


def confirm(ask, token, facts):
    if ask(f'{facts}\nType {token} to attest: ') != token:
        raise ValueError('confirmation')


def observed_checks(ask, post):
    checks = dict.fromkeys(h.POST, False)
    for group, fields in GROUPS.items():
        names = fields.split()
        if group == 'C06' and post:
            names += h.POST
        confirm(ask, group, 'Reviewed ' + group + ' checks: ' + ', '.join(names))
        checks.update(dict.fromkeys(names, True))
    return checks


def make_profile(ask, visible):
    # Ask for independently reviewed source IDs. Never infer approval from local HEAD.
    commit = visible('Reviewed wrapper commit: ')
    tree = visible('Reviewed wrapper tree: ')
    root = h.private_directory(ask('Private root: '))
    config = h.private_directory(ask('Empty Docker configuration directory: '))
    binaries = {}
    for name in (*h.BINS, 'dockerd'):
        entry = Path(visible('Installed absolute path for ' + name + ': '))
        if not entry.is_absolute():
            raise ValueError('path')
        real = entry.resolve(strict=True)
        binaries[name] = dict(path=str(real), sha256=h.sha(h.read(real, 268435456)))
    daemon = binaries.pop('dockerd')
    row = dict(schema='ha-private-host-profile/1', source_commit=commit, source_tree=tree,
               private_root=str(root), client_config=str(config), binaries=binaries,
               dockerd_sha256=daemon['sha256'])
    h.profile(row)
    return row


def receipt(p, operation, state, checks, when, post=False):
    if state not in ('PRESENT', 'ABSENT') or not h.hashed(operation):
        raise ValueError('custody')
    row = dict(schema='ha-separate-account-custody-return/1', status='OBSERVED',
               observed_at_with_offset=when.isoformat(), operation_id=operation,
               private_profile_commitment_sha256=h.sha(h.canonical(p)),
               reviewed_source_commit=p['source_commit'], reviewed_source_tree=p['source_tree'],
               raw_private_evidence_retained_by='Howard', raw_private_values_included=False,
               docker_users_group_state=state, engine_kind='PRIVATE_DISTRO_ENGINE',
               public_host_qualification='PENDING', qualification_receipt_sha256=None, checks=checks,
               administrators_including_howard_trusted=True, no_swap_required=False,
               no_hibernation_required=False, crash_dump_controls_required=False,
               execution_authorized=False)
    h.custody(row, operation, row['private_profile_commitment_sha256'],
              p['source_commit'], p['source_tree'], post=post)
    return row


def load_file(folder, name):
    path = folder / name
    h.private_control_file(path)
    return h.read(path)


def emit(folder, name, raw):
    path = folder / name
    h.exclusive(path, raw)
    h.private_control_file(path)
    print(name, h.sha(raw))


def operate(mode, folder, ask, *, visible, now=utc):
    if mode == 'PREFLIGHT':
        if any(folder.iterdir()):
            raise ValueError('fresh-directory')
        p = make_profile(ask, visible)
        state = ask('Observed docker-users group state (PRESENT or ABSENT): ')
        checks = observed_checks(ask, False)
        operation = secrets.token_hex(32)
        row = receipt(p, operation, state, checks, now())
        emit(folder, 'OPERATION-ID.txt', (operation + '\n').encode('ascii'))
        emit(folder, 'PROFILE.json', h.canonical(p))
        emit(folder, 'CUSTODY.json', h.canonical(row))
        return

    p = h.strict(load_file(folder, 'PROFILE.json'))
    h.profile(p)
    raw_id = load_file(folder, 'OPERATION-ID.txt')
    operation = raw_id.decode('ascii').removesuffix('\n')
    if not h.hashed(operation) or raw_id != (operation + '\n').encode('ascii'):
        raise ValueError('operation')
    pre_raw = load_file(folder, 'CUSTODY.json')
    pre = h.strict(pre_raw)
    profile_hash = h.sha(h.canonical(p))
    h.custody(pre, operation, profile_hash, p['source_commit'], p['source_tree'])
    start = h.aware(pre['observed_at_with_offset'])
    if mode in MODES:
        try:
            minutes = int(ask('Window in whole minutes from preflight (1 through 120): '))
        except ValueError:
            raise ValueError('window') from None
        if not 1 <= minutes <= 120:
            raise ValueError('window')
        confirm(ask, mode, 'Howard authorizes only this public H1 operation for this profile and custody.')
        row = dict(schema='ha-operation-approval/1', authority='Howard', operation_id=operation,
                   mode=mode, profile_sha256=profile_hash, custody_sha256=h.sha(pre_raw),
                   source_commit=p['source_commit'], source_tree=p['source_tree'],
                   valid_from=start.isoformat(), expires_at=(start + timedelta(minutes=minutes)).isoformat(),
                   public_only=True)
        raw = h.canonical(row)
        h.approval(row, h.sha(raw), raw, p, mode, now())
        emit(folder, mode + '-APPROVAL.json', raw)
    elif mode == 'POSTFLIGHT':
        raw = load_file(folder, 'QUALIFY_PUBLIC-APPROVAL.json')
        approved = h.strict(raw)
        if (approved['custody_sha256'] != h.sha(pre_raw) or approved['operation_id'] != operation
                or h.aware(approved['valid_from']) != start):
            raise ValueError('join')
        confirm(ask, 'POSTFLIGHT', 'H1 is now waiting at its postflight prompt.')
        state = ask('Observed docker-users group state (PRESENT or ABSENT): ')
        if state != pre['docker_users_group_state']:
            raise ValueError('changed-custody')
        checks = observed_checks(ask, True)
        when = now()
        h.approval(approved, h.sha(raw), raw, p, 'QUALIFY_PUBLIC', when)
        emit(folder, 'POSTFLIGHT.json', h.canonical(receipt(p, operation, state, checks, when, True)))
    else:
        raise ValueError('mode')


def main(argv):
    if (os.name != 'posix' or os.getuid() == 0 or os.environ.get('CI') or os.environ.get('GITHUB_ACTIONS')
            or not all(stream.isatty() for stream in (sys.stdin, sys.stdout, sys.stderr))
            or len(argv) != 1 or argv[0] not in ('PREFLIGHT', *MODES, 'POSTFLIGHT')):
        raise ValueError('attended-only')
    # Echo reviewed source IDs and installed binary paths only. Hide custody and private paths.
    with open('/dev/tty', 'w', encoding='utf-8') as tty, warnings.catch_warnings():
        warnings.simplefilter('error', getpass.GetPassWarning)
        def ask(prompt):
            return getpass.getpass(prompt, stream=tty)
        os.umask(0o077)
        folder = h.private_directory(ask('Exclusive control directory (outside checkout): '))
        if folder.is_relative_to(h.ref.ROOT.resolve()):
            raise ValueError('control-directory')
        operate(argv[0], folder, ask, visible=input)


CONTROL_CODES = frozenset({
    'attended-only', 'changed-custody', 'confirmation', 'control-directory',
    'custody', 'fresh-directory', 'join', 'mode', 'operation', 'path', 'window',
})


def cli(argv):
    try:
        main(argv)
    except (Exception, KeyboardInterrupt) as error:
        code = 'operator-fault'
        if isinstance(error, ValueError) and len(error.args) == 1:
            candidate = error.args[0]
            if type(candidate) is str and (candidate in CONTROL_CODES or candidate in h.CODES):
                code = candidate
        print('operator-controls-refused', code, file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(cli(sys.argv[1:]))
