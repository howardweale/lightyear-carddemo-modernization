"""One approved journey group, serial immutable slots, terminal finalization.

No CLI or model transport. Calling this is native Docker execution and requires
the exact public executable plan commit and its separately signed window approval.
"""
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import time
import zipfile
import os
import subprocess
import sys
from lightyear_calibration.contracts import canonical, read_json, verify
from lightyear_calibration.journey_order import file_hash
from lightyear_control_tower.decisions import verify_envelope
from tools.ms94_b06_admission import check, sign_once, bound_file, utc
from tools.ms94_b06_executable import verify_snapshot

J1_REPLAY_CONTEXT = (
    'factory/idempiere/qualification/public/operations.json',
    'factory/idempiere/qualification-ms94-v3/public/operations.json',
    'work/ms87/operator/authority.public.pem',
)


def replay_context(root, destination, run, public_key):
    """Restore the unchanged J1 judge's expected layout, with public files only.

    The native archive is untouched. No signature is replaced and no private
    authority is copied. Bound implementation/class bytes still use `root`.
    """
    from lightyear_calibration.journey_order import RUNS
    root, destination = Path(root), Path(destination)
    plan = read_json(Path(run) / 'plan.json'); verify(plan)
    if plan['journey'] == 'J1':
        manifest = read_json(root / 'b06-executable-snapshot.json'); verify(manifest)
        for name in J1_REPLAY_CONTEXT:
            check(name in manifest['files_sha256'], 'qualification-replay-context-unbound')
            raw = bound_file(root, name, manifest['files_sha256'][name]).read_bytes()
            if name.endswith('.pem'):
                check(raw == public_key, 'qualification-replay-key-differs')
            target = destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open('xb') as stream: stream.write(raw)
    parent = destination / RUNS
    parent.mkdir(parents=True, exist_ok=True)
    return parent


def supervised(stage, root, run, directory, authority, deadline):
    """One deadline covers native work, archive, replay, cleanup and signing."""
    from tools.ms94_b05_supervisor import wait_process, terminate
    check(time.monotonic() < deadline, 'qualification-finalization-deadline')
    command = [sys.executable, '-m', 'tools.ms94_b06_qualification_worker', '--stage', stage,
               '--root', str(root), '--run', str(run), '--output', str(directory), '--authority', str(authority)]
    environment = {**os.environ, 'PYTHONPATH': os.pathsep.join((str(root/'src'), str(root))),
                   'PYTHONUTF8': '1', 'PYTHONDONTWRITEBYTECODE': '1'}
    options = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {'start_new_session': True}
    with (directory/(run.name+'-'+stage+'.stdout')).open('xb') as stdout, \
         (directory/(run.name+'-'+stage+'.stderr')).open('xb') as stderr:
        process = subprocess.Popen(command, cwd=root, env=environment, stdout=stdout, stderr=stderr, **options)
        try:
            wait_process(process, deadline)
        finally:
            terminate(process)
    path = run/'receipt.json' if stage == 'native' else directory/(run.name+'-audit.json')
    return read_json(path)


def recovery(root, run, signer, directory):
    """Only the just-authorized pair, after its worker tree has terminated."""
    from lightyear_calibration.journey_runtime import LocalRunner
    from lightyear_calibration.measured_native import cleanup_owned
    plan = read_json(run/'plan.json'); auth = read_json(run/'authorization.json')
    check(verify_envelope(auth, signer.public) and auth['run_id'] == run.name and
          auth['plan']['plan_sha256'] == plan['content_sha256'], 'qualification-recovery-ownership')
    before = time.monotonic()
    runner = LocalRunner(root, run, plan, lambda *_: None)
    cleaned = cleanup_owned(runner)
    check(cleaned['complete'], 'qualification-recovery-cleanup-failed')
    absence = cleanup_check(run)
    return sign_once(directory/(run.name+'-recovery.json'), {
        'artifact_type': 'ms94-b06-qualification-recovery/1', 'plan_sha256': plan['content_sha256'],
        'cleanup': cleaned, 'actual_absence': absence, 'outside_valid_trial_budget': True,
        'elapsed_seconds': round(time.monotonic()-before, 3), 'model_calls': 0}, signer)


def cleanup_check(run):
    """Read-only actual checks; never delete any resource during independent replay."""
    from lightyear_calibration.journey_runtime import docker
    run = Path(run)
    inventory = read_json(run / 'resources.json')['resources']
    check(inventory and len({(r['kind'], r['name']) for r in inventory}) == len(inventory),
          'qualification-resource-inventory-invalid')
    for row in inventory:
        check(row['kind'] in ('container','network','volume') and row['name'].startswith(run.name+'-'),
              'qualification-resource-not-owned')
    for kind in ('container','network','volume'):
        flags = ['-a'] if kind == 'container' else []
        check(not docker(kind,'ls',*flags,'-q','--filter','label=lightyear.journey='+run.name).stdout.strip(),
              'qualification-owned-resource-remains')
        for row in (r for r in inventory if r['kind'] == kind):
            fmt = '{{.Names}}' if kind == 'container' else '{{.Name}}'
            names = docker(kind,'ls',*flags,'--format',fmt).stdout.decode().splitlines()
            check(row['name'] not in names, 'qualification-recorded-resource-remains')
    return {'actual_owned_cleanup_verified': True, 'resources_checked': len(inventory)}


def archive_run(run, path):
    run, path = Path(run), Path(path)
    check(not path.exists(), 'qualification-archive-already-exists')
    with zipfile.ZipFile(path, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
        for item in sorted(run.rglob('*')):
            check(not item.is_symlink(), 'qualification-archive-symlink')
            if item.is_file():
                check(not item.name.endswith('.key.pem'), 'qualification-private-key-in-run')
                archive.write(item, (Path(run.name) / item.relative_to(run)).as_posix())
    return file_hash(path)


def finalize(root, run, directory, public_key, signer):
    """Replay the actual zipped bytes, then recheck absence after offline replay."""
    from tools.ms94_b06_qualification_replay import replay_pair
    run, directory = Path(run), Path(directory)
    before = cleanup_check(run)
    archive = directory / (run.name + '.zip')
    sha = archive_run(run, archive)
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix='b06-offline-', dir=directory) as temporary:
        parent = replay_context(root, Path(temporary), run, public_key)
        with zipfile.ZipFile(archive) as stream:
            for info in stream.infolist():
                name = Path(info.filename)
                check(not name.is_absolute() and '..' not in name.parts and name.parts[0] == run.name,
                      'qualification-archive-path')
            stream.extractall(parent)
        replayed = replay_pair(root, parent / run.name, public_key)
    check(file_hash(archive) == sha, 'qualification-archive-changed')
    after = cleanup_check(run)
    # Gate details contain native private values: keep this signed audit LOCAL.
    return sign_once(directory / (run.name + '-audit.json'), {
        'artifact_type': 'ms94-b06-qualification-slot-audit/1', 'archive_sha256': sha,
        'run_id': run.name, 'replay': replayed, 'cleanup_before': before, 'cleanup_after': after,
        'independent_replay_seconds': round(time.monotonic()-started,3), 'model_calls': 0,
        'review': 'operator review; not independent attestation'}, signer)


def intended(plan, result):
    """No generic 'any failure is a killed mutant' acceptance."""
    expected = plan['expected']; actual = result['replay']
    check(actual['full_entry_replayed'] is True, 'qualification-entry-not-replayed')
    if plan['control'] == 'genuine-equipment-fault':
        check(actual.get('database_fault_replayed') is True and actual['equipment_suspect'] is True,
              'qualification-equipment-hook-not-replayed')
        return
    check(actual['clock_replayed'] is True, 'qualification-clock-not-replayed')
    status = expected.get('status')
    if status == 'rejected':
        check(actual.get('native_mutation_replayed') is True, 'qualification-specific-mutant-not-replayed')
    elif status is not None:
        check(actual['status'] == status, 'qualification-unexpected-status')
    if 'equipment_suspect' in expected:
        check(actual['equipment_suspect'] == expected['equipment_suspect'], 'qualification-unexpected-suspicion')
    if 'diagnostics' in expected:
        check(actual['diagnostics'] == expected['diagnostics'], 'qualification-unexpected-diagnostics')
    if 'closed_reason' in expected and status != 'rejected':
        check((actual.get('gate') or {}).get('closed_reason') == expected['closed_reason'],
              'qualification-unexpected-closed-reason')
    if plan.get('slot_kind') == 'evidence-boundary':
        check(actual.get('evidence_boundary_replayed') is True, 'qualification-boundary-not-replayed')
    if status == 'passed':
        check(actual['complete_gate_replayed'] and actual['diagnostic_replayed'] and actual['observer_replayed'],
              'qualification-reference-not-complete')
    if expected.get('delivery') == 'builder-direct':
        check(actual.get('delivered') is True and actual['delivery_replayed'] is True and
              actual['diagnostics'] and all(d['category'] == 'candidate-runtime-exception' and
              d['thrown_by'] == 'candidate' for d in actual['diagnostics']), 'qualification-direct-delivery-missing')
    if expected.get('delivery') == 'empty':
        check(actual['diagnostics'] == [] and actual.get('delivered', False) is False,
              'qualification-unexpected-feedback')
    if expected.get('delivery') == 'qualified-closed-projection-to-zero-model-sink':
        check(actual.get('delivered') is True and actual['delivery_replayed'] is True and
              actual['diagnostics'] and all(d['category']=='candidate-posting-sequence-misuse'
              for d in actual['diagnostics']), 'qualification-posting-delivery-not-observed')
    if 'cause' in expected or expected.get('attribution_available') is not None:
        # Native cause and its recorded closed delivery must be replayed; the
        # ordinary runtime exception route cannot qualify posting attribution.
        check(actual.get('posting_control_replayed') is True, 'qualification-posting-control-not-replayed')
        if 'cause' in expected:
            check(all(v['cause'] == expected['cause'] for v in actual['posting_causes'].values()),
                  'qualification-unexpected-posting-cause')


def preliminary(plan, receipt, cleanup):
    """Signal unexpected native outcomes before expensive independent replay."""
    check(cleanup['complete'] is True, 'qualification-native-cleanup-failed')
    expected = plan['expected']
    if 'equipment_suspect' in expected:
        check(receipt['equipment_suspect'] == expected['equipment_suspect'], 'qualification-unexpected-suspicion')
    elif plan['control'] != 'genuine-equipment-fault' and plan.get('slot_kind') != 'evidence-boundary':
        check(not receipt['equipment_suspect'], 'qualification-unexpected-suspicion')
    status = expected.get('status')
    if status and status != 'rejected':
        check(receipt['status'] == status, 'qualification-unexpected-status')
    if status == 'rejected':
        allowed = ('execution-failure',) if plan['control']=='duplicate-trace-key' else ('business-failure', 'contract-violation')
        check(receipt['status'] in allowed, 'qualification-unexpected-mutant-status')
    check(receipt['status'] != 'equipment-failure' or plan['control'] == 'genuine-equipment-fault',
          'qualification-equipment-failure')


def execute_group(root, group, directory, signer, *, authority_root, tower_reader=None):
    """Single-use entry. Merely converting/publishing a plan cannot call Docker."""
    check(group.get('content_sha256')!='aa22263615aaaf143cf3eda22330fdfbba64dfc08a21dc017bd59e5b58522d9b',
          'r11-withdrawn-unqualified-generated-provenance')
    from tools.ms94_b06_engineering_boundary import refuse_engineering
    refuse_engineering(group, directory)
    root, directory = Path(root).resolve(), Path(directory).resolve()
    authority_root = Path(authority_root).resolve()
    from lightyear_calibration.journey_runtime import CONTROL
    check(not authority_root.is_relative_to(root) and
          (authority_root/CONTROL/'authority.public.pem').read_bytes() == signer.public and
          (authority_root/CONTROL/'authority.key.pem').is_file(), 'qualification-existing-authority-binding')
    verify(group); verify_snapshot(root, group['snapshot_sha256'])
    check(group['model_calls'] == 0 and group['measurement_authorized'] is False, 'qualification-only')
    publication = read_json(directory / 'publication.json')
    check(verify_envelope(publication, signer.public) and publication['public_bytes_verified'] is True and
          publication['plan_sha256'] == group['content_sha256'] and
          publication['snapshot_sha256'] == group['snapshot_sha256'], 'qualification-public-plan-not-bound')
    check(not any((directory/n).exists() for n in ('started.json','report.json','stopping.json')),
          'qualification-group-already-attempted')
    from tools.ms94_b06_group_decision import authorize
    from lightyear_control_tower.b06 import atomic_new
    proof = authorize(group, publication['public_commit'], tower_reader, signer.public)
    atomic_new(directory/'tower-authorization.json', proof)
    authorization_sha = proof['decision_sha256']
    started = time.monotonic(); now = lambda: datetime.now(timezone.utc)
    spec = group['docker_run_window']; rows = []; attempted = []; failure = None
    def stopping(slot, exc):
        nonlocal failure
        if failure is None:
            failure = {'slot_id':slot['id'], 'exception_type':type(exc).__name__}
        if not (directory/'stopping.json').exists():
            sign_once(directory/'stopping.json', {'artifact_type':'ms94-b06-qualification-stop/1',
                'plan_sha256':group['content_sha256'], 'failure':failure,
                'real_utc':now().isoformat(), 'model_calls':0}, signer)
            print('B06 qualification stopped: '+slot['id']+'; preserve evidence; no next slot.', flush=True)
    check(utc(spec['not_before_utc']) <= now() < utc(spec['deadline_utc']), 'qualification-outside-window')
    sign_once(directory/'started.json', {'artifact_type':'ms94-b06-qualification-start/1',
        'plan_sha256':group['content_sha256'], 'authorization_sha256':authorization_sha,
        'started_utc':now().isoformat(), 'model_calls':0}, signer)
    for slot in group['slots']:
        run = None; authorized = False
        try:
            run = bound_file(root,slot['plan_path'],slot['plan_file_sha256']).parent
            verify_snapshot(root,group['snapshot_sha256'])
            plan=read_json(run/'plan.json'); verify(plan)
            check(plan['content_sha256'] == slot['plan_sha256'] and plan['slot_id'] == slot['id'], 'qualification-slot-changed')
            check((utc(spec['deadline_utc'])-now()).total_seconds() >= plan['declaration']['policy']['max_elapsed_seconds'],
                  'qualification-no-full-slot-window')
            check(not (run/'started.json').exists() and not (run/'authorization.json').exists(), 'qualification-slot-restart')
            sign_once(run/'authorization.json', {'scope':'zero-model-native-qualification','run_id':run.name,
                'plan':{'plan_sha256':plan['content_sha256']},'docker_run_window':spec,
                'group_authorization_sha256':authorization_sha}, signer)
            authorized = True
            trial_started=time.monotonic()
            deadline = min(trial_started + plan['declaration']['policy']['max_elapsed_seconds'],
                           trial_started + (utc(spec['deadline_utc'])-now()).total_seconds())
            attempted.append(slot['id'])
            receipt=supervised('native',root,run,directory,authority_root,deadline)
            check(verify_envelope(receipt, signer.public), 'qualification-native-receipt-signature')
            try:
                preliminary(plan, receipt, read_json(run/'cleanup.json'))
            except Exception as exc:
                stopping(slot, exc)  # visible and signed BEFORE lengthy replay
            # Preserve and audit a failed outcome too, but never start another.
            audit=supervised('finalize',root,run,directory,authority_root,deadline)
            check(verify_envelope(audit, signer.public), 'qualification-audit-signature')
            rows.append({'slot_id':slot['id'],'receipt_sha256':receipt['content_sha256'],
                         'audit_sha256':audit['content_sha256'],'status':receipt['status']})
            check(time.monotonic()-trial_started < plan['declaration']['policy']['max_elapsed_seconds'] and
                  now() < utc(spec['deadline_utc']), 'qualification-finalization-deadline')
            verify_snapshot(root,group['snapshot_sha256'])
            if failure is not None: break
            intended(plan,audit)
            sign_once(directory/(slot['id']+'-progress.json'),{'artifact_type':'ms94-b06-qualification-progress/1',
                'plan_sha256':group['content_sha256'],'completed':list(rows),'model_calls':0},signer)
        except Exception as exc:
            stopping(slot, exc)
            if authorized and run is not None:
                try:
                    recovery(root, run, signer, directory)
                except Exception as cleanup_error:
                    sign_once(directory/(run.name+'-recovery-failure.json'), {
                        'artifact_type':'ms94-b06-qualification-recovery-failure/1',
                        'exception_type':type(cleanup_error).__name__, 'model_calls':0}, signer)
            break
    purpose = ({'purpose': group['purpose'], 'qualification_credit': False}
               if group.get('purpose') in ('five-path-provenance-census', 'observer-native-practice') else {})
    return sign_once(directory/'report.json',{**purpose, 'artifact_type':'ms94-b06-qualification-terminal/1',
        'plan_sha256':group['content_sha256'],'snapshot_sha256':group['snapshot_sha256'],
        'passed':failure is None and len(rows)==len(group['slots']), 'failure':failure,'completed':rows,
        'attempted':attempted,
        'unstarted':[s['id'] for s in group['slots'] if s['id'] not in attempted],
        'unfinalized':[s for s in attempted if s not in {r['slot_id'] for r in rows}],
        'elapsed_seconds':round(time.monotonic()-started,3),'model_calls':0,
        'measurement_authorized':False,'review':'operator review; not independent attestation'},signer)
