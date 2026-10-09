"""One-way, zero-model native plan assembly; never authorize or run Docker.

The caller supplies real private inputs and compiled target bytes. Missing
inputs leave an unsealed preparation directory, not an executable snapshot.
"""
import copy
import hashlib
import re
from uuid import NAMESPACE_URL, uuid5
from pathlib import Path

from lightyear_calibration.contracts import canonical, read_json, seal, verify
from lightyear_calibration.journey_order import RUNS, file_hash
from lightyear_control_tower.status_export import atomic_new
from tools.ms94_b06_admission import bound_file, check, verify_inputs, utc
from tools.ms94_b06_runtime_contract import runtime_contract
from tools.ms94_b06_runtime_delivery import POLICY


def native_run_name(revision, slot_id):
    """Keep logical schedule IDs separate from the native resource-owner ID."""
    check(all(isinstance(v, str) and re.fullmatch(r'[a-z0-9-]+', v)
              for v in (revision, slot_id)), 'native-run-identity')
    return 'journey-' + uuid5(NAMESPACE_URL, 'lightyear/b06/' + revision + '/' + slot_id).hex


def validate_native_owner(run):
    # Use the actual inherited network policy before writing or freezing inputs.
    # Do not widen that policy or change J1's business predicates.
    from lightyear_execution.journey_network import InternalOnlyNetwork
    InternalOnlyNetwork(Path(run).name)


def window(calendar, start, end):
    verify(calendar)
    a, b = utc(start), utc(end)
    check(utc(calendar['period_start_utc']) <= a < b < utc(calendar['period_end_exclusive_utc']),
          'group-window-outside-period')
    check((b - a).total_seconds() <= calendar['maximum_seconds'], 'group-window-exceeds-cap')
    check((utc(calendar['period_end_exclusive_utc']) - a).total_seconds() > calendar['maximum_seconds'],
          'group-latest-launch-exceeded')
    return {'not_before_utc': a.isoformat(), 'deadline_utc': b.isoformat(),
            'run_definition': 'one journey qualification group; serial fresh pairs; no restart',
            'docker_approved': False}


def assemble_slot(root, run, base, slot, input_files):
    """Create exact native inputs/plan in a new slot. No signatures or execution."""
    root, run = Path(root).resolve(), Path(run).resolve()
    check(run.parent == (root / RUNS).resolve(), 'slot-run-path')
    check(not run.exists() and re.fullmatch(r'[a-z0-9-]+', run.name), 'slot-already-exists')
    validate_native_owner(run)
    check(base['journey'] in ('J1', 'J2', 'J3') and base['model_calls'] == 0 and
          base['qualification_only'] is True, 'slot-not-qualification')
    check(base['declaration']['policy']['max_model_calls'] == 0, 'declaration-model-budget')
    verify(base['calendar'])
    check(base['calendar']['clock_mode'] == 'unmodified-real-time', 'slot-clock-policy')
    proposed_window = base['docker_run_window']
    check(proposed_window == window(base['calendar'], proposed_window['not_before_utc'],
                                    proposed_window['deadline_utc']), 'slot-window-binding')
    plan = copy.deepcopy(base)
    plan.pop('content_sha256', None)
    check('authorization' not in plan, 'assembly-cannot-authorize')
    plan.update(artifact_type='ms94-b06-native-pair-plan/1', execution_admission_version=3, slot_id=slot['id'],
                control=slot['control'], expected=slot['expected'])
    plan['slot_kind'] = slot['kind']
    if 'fault_recipe' in slot: plan['fault_recipe'] = copy.deepcopy(slot['fault_recipe'])
    plan['fault'] = slot['control'] if slot['kind'] == 'native-mutator' else 'none'
    from tools.ms94_b06_qualification_controls import validate_plan
    validate_plan(plan)
    data = {}
    for name, item in input_files.items():
        check(Path(name).name == name and name not in ('.', '..'), 'slot-input-name')
        data[name] = bound_file(root, item['path'], item['sha256']).read_bytes()
    plan['inputs_sha256'] = {n: hashlib.sha256(b).hexdigest() for n, b in data.items()}
    check(plan['inputs_sha256']['operations.java'] == slot['source']['sha256'], 'slot-source-differs')
    plan['harness_sha256'] = plan['inputs_sha256']['operations.java']
    from tools.ms94_b06_register_inputs import validate_files
    validate_files(plan['journey'], data, plan['assessed_on'], plan['comparison_register_sha256'])
    if plan['journey'] != 'J1':
        import json
        plan['private_expectations_sha256'] = hashlib.sha256(canonical(
            json.loads(data['private-expectations.json']))).hexdigest()
    plan['evidence_contract'] = {'clock_stages': ['before', 'after'], 'runtime': runtime_contract(plan, run.name)}
    plan['runtime_delivery'] = {'policy_sha256': file_hash(root / POLICY),
                                'consumer': 'zero-model-preflight-inbox/1'}
    if slot['control'] == 'genuine-equipment-fault':
        from tools.ms94_b06_fault_hook import TRIGGER
        plan['native_fault_hook'] = {'kind': 'owned-database-stop', 'lane': slot['target_lane'], 'trigger': TRIGGER}
    required_code = {p.relative_to(root).as_posix(): file_hash(p)
                     for folder in ('src', 'tools') for p in (root / folder).rglob('*.py')}
    check(required_code and all(plan['implementation_sha256'].get(n) == h for n, h in required_code.items()),
          'slot-implementation-closure')
    for name, sha in plan['implementation_sha256'].items(): bound_file(root, name, sha)
    spec = plan['posting_observer']
    from tools.ms94_b06_bytecode_policy import validate_policy
    validate_policy(spec)
    from tools.ms94_b06_posting_replay import catalog, TERMINAL
    classes = catalog(root, spec['target_class_files_sha256'])
    if 'built_runtime' in plan:
        from tools.ms94_b06_built_runtime import contract
        contract(root, plan)
    if spec.get('observer_binding_v2') is not None:
        from tools.ms94_b06_observer_v2 import load_manifest
        load_manifest(root, spec, plan.get('built_runtime', {}).get('image', plan['local']['runner_image']))
    if spec.get('forwarding_stub') is not None:
        from tools.ms94_b06_forwarding_stub import validate_spec
        validate_spec(spec, classes)
    from tools.ms94_b06_lock_sql import bind
    lock = spec['lock_sql']
    check(spec['target_class_files_sha256'].get(lock['class_file']) == lock['class_sha256'], 'slot-lock-catalog')
    bind(bound_file(root, lock['class_file'], lock['class_sha256']).read_bytes(), lock)
    check(TERMINAL in classes and 'org.junit.platform.engine.support.hierarchical.NodeTestTask' in classes,
          'slot-terminal-catalog-incomplete')
    check(re.fullmatch('[a-f0-9]{64}', spec['java_binary_sha256']) is not None, 'slot-java-binding')
    check(bool(spec['class_files_sha256']), 'slot-observer-uncompiled')
    for name, sha in spec['class_files_sha256'].items(): bound_file(root / spec['classes_directory'], name, sha)
    run.mkdir(parents=True, exist_ok=False)
    (run / 'inputs').mkdir()
    for name, content in data.items():
        with (run / 'inputs' / name).open('xb') as stream: stream.write(content)
    plan = seal(plan)
    verify_inputs(run, plan)
    atomic_new(run / 'plan.json', plan)
    return plan


def freeze(source, destination, bindings, slot_plans):
    """Exclusive new directory, verified copies, final manifest written last.

    Output permissions alone are not the integrity boundary: every execution
    must recheck this manifest. A failed copy stays present and cannot be reused.
    """
    source, destination = Path(source).resolve(), Path(destination).resolve()
    check('work/ms94' not in destination.as_posix().lower(), 'protected-freeze-path')
    check(destination.parent.name == 'b06-execution-snapshots', 'wrong-freeze-parent')
    check(not destination.exists() and bindings and slot_plans, 'freeze-existing-or-empty')
    check('b06-executable-snapshot.json' not in bindings, 'recursive-manifest')
    for name, sha in bindings.items(): bound_file(source, name, sha)
    for name, expected in slot_plans.items():
        path = source / name
        validate_native_owner(path.parent)
        plan = read_json(path); verify(plan)
        check(plan['content_sha256'] == expected and name in bindings, 'freeze-slot-plan')
        verify_inputs(path.parent, plan)
        if plan.get('journey') == 'J1':
            from tools.ms94_b06_qualification_driver import J1_REPLAY_CONTEXT
            check(all(n in bindings for n in J1_REPLAY_CONTEXT), 'freeze-J1-replay-context-missing')
        required = {**plan['implementation_sha256'], POLICY: file_hash(source / POLICY), **{
            (path.parent.relative_to(source) / 'inputs' / n).as_posix(): h
            for n, h in plan['inputs_sha256'].items()},
            **plan['posting_observer']['target_class_files_sha256'],
            **{(Path(plan['posting_observer']['classes_directory']) / n).as_posix(): h
               for n, h in plan['posting_observer']['class_files_sha256'].items()}}
        if 'built_runtime' in plan:
            from tools.ms94_b06_built_runtime import required_inputs
            required.update(required_inputs(plan['built_runtime']))
        if plan['posting_observer'].get('observer_binding_v2') is not None:
            from tools.ms94_b06_observer_v2 import load_manifest
            spec = plan['posting_observer']; ref = spec['observer_binding_v2']
            manifest, _ = load_manifest(source, spec, plan.get('built_runtime', {}).get('image', plan['local']['runner_image']))
            required[ref['path']] = ref['sha256']
            for row in manifest['classes']:
                required[row['path']] = row['sha256']
                if row.get('archive_path'):
                    required[row['archive_path']] = manifest['runtime_files'][row['origin']]
        check(all(bindings.get(n) == h for n, h in required.items()), 'freeze-input-closure')
    destination.mkdir(parents=True, exist_ok=False)
    for name, sha in bindings.items():
        target = destination / name; target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as stream: stream.write(bound_file(source, name, sha).read_bytes())
        bound_file(destination, name, sha)
    record = seal({'artifact_type': 'ms94-b06-executable-snapshot/1', 'files_sha256': bindings,
                   'slot_plans_sha256': slot_plans, 'model_calls': 0,
                   'docker_authorized': False, 'immutable_path': destination.name})
    atomic_new(destination / 'b06-executable-snapshot.json', record)
    return record


def verify_snapshot(root, expected):
    root = Path(root)
    manifest = read_json(root / 'b06-executable-snapshot.json'); verify(manifest)
    check(manifest['content_sha256'] == expected, 'snapshot-identity')
    for name, sha in manifest['files_sha256'].items(): bound_file(root, name, sha)
    return manifest
