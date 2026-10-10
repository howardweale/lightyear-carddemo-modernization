"""Offline replay of external JVM checkpoints and native SQL readbacks.

This verifies collection, not causal attribution or qualification. In particular,
a signed assertion that an equipment fault was absent is never sufficient.
"""
import hashlib
import json
import re
from pathlib import Path

from lightyear_calibration.contracts import read_json, verify, digest
from lightyear_calibration.b06_posting_probe import queries_for
from lightyear_control_tower.decisions import verify_envelope
from tools.ms94_b06_admission import check, bound_file, replay_entry, replay_clocks
from tools.ms94_b06_classfile import inspect_class

SUPPORT = 'org.idempiere.test.JourneySupport'
CANDIDATE = 'org.idempiere.test.LightyearOperationsTest'
TERMINAL = 'org.junit.platform.launcher.core.ExecutionListenerAdapter'
TERMINAL_SIGNATURE = '(Lorg/junit/platform/engine/TestDescriptor;Lorg/junit/platform/engine/TestExecutionResult;)V'
FRAMEWORK = {'org.compiere.model.PO', 'org.compiere.acct.Doc', 'org.compiere.acct.DocManager', 'org.compiere.util.DB'}
TARGETS = {'org.compiere.util.DB': {'executeUpdate(Ljava/lang/String;Ljava/lang/String;)I'}, SUPPORT: {'postOnce(Lorg/compiere/model/PO;[Lorg/compiere/model/MAcctSchema;)V'},
           'org.compiere.model.PO': {'lock()Z'},
           'org.compiere.acct.Doc': {'post(ZZZ)Ljava/lang/String;'},
           'org.compiere.acct.DocManager': {
               'postDocument([Lorg/compiere/model/MAcctSchema;IIZZLjava/lang/String;)Ljava/lang/String;'}}


def catalog(root, bindings):
    """Recompute identities from bound compiled bytes; ignore asserted identities."""
    result = {}
    for name, expected in bindings.items():
        raw=bound_file(root, name, expected).read_bytes()
        item = inspect_class(raw)
        item['class_bytes_hex']=raw.hex()
        check(item['class'] not in result, 'observer-duplicate-class-identity')
        result[item['class']] = item
    check({SUPPORT, CANDIDATE, *FRAMEWORK} <= set(result), 'observer-class-catalog-incomplete')
    return result


def checked_frames(event, classes, loaders, definitions=None, stub_policy=None, host_entries=None):
    frames = event['frames']
    check(isinstance(frames, list) and frames, 'observer-stack-empty')
    frames = [dict(f) for f in frames]
    for frame in frames:
        frame.pop('_verified_forwarding_host', None)
    for index, frame in enumerate(frames):
        name = frame['class']
        if stub_policy is not None:
            from tools.ms94_b06_forwarding_stub import POLICY, validate_stub
            check(stub_policy == {'policy':POLICY, 'adjacent_target':'younger'}, 'observer-stub-policy')
            raw = (definitions or {}).get(frame.get('definition_id'))
            check(raw is not None and all(raw[k] == frame[k] for k in
                  ('class','method','signature','loader','constant_pool_sha256','method_sha256')),
                  'observer-frame-definition-missing-or-differs')
            if name not in classes and '/' in name:
                proof = validate_stub(raw, frame, frames[index-1] if index else None, classes, host_entries or {})
                frame['_verified_forwarding_host'] = proof['host_class']
                loaders.setdefault(name, frame['loader'])
                check(loaders[name] == frame['loader'], 'observer-class-loader-changed')
                continue
        if name in classes or name == SUPPORT or name.startswith(CANDIDATE) or name in FRAMEWORK or name.startswith(('org.junit.', 'org.opentest4j.', 'junit.framework.')):
            check(name in classes, 'observer-unbound-class')
            expected = classes[name]
            check(frame['constant_pool_sha256'] == expected['constant_pool_sha256'] and
                  frame['method_sha256'] == expected['methods'].get(frame['method'] + frame['signature']),
                  'observer-executed-bytecode-differs')
            loaders.setdefault(name, frame['loader'])
            check(loaders[name] == frame['loader'], 'observer-class-loader-changed')
    return frames


def origin(frames):
    # Inspect the nearest caller, not an arbitrary candidate deeper in the stack.
    # Unknown helpers remain outside-origin even when called by the candidate.
    for frame in frames[1:]:
        name = frame.get('_verified_forwarding_host', frame['class'])
        if name in FRAMEWORK:
            continue
        if name == SUPPORT:
            return 'support'
        if name == CANDIDATE or name.startswith(CANDIDATE + '$'):
            return 'candidate'
        return 'outside'
    return 'outside'


def replay_stream(folder, receipt, classes, lane, stub_policy=None, host_entries=None, binding_v2=None):
    """Pure content verification; caller must authenticate receipt and full entry."""
    check(not receipt.get('diagnostic_only') and not receipt.get('unmatched_return_policy'),
          'observer-diagnostic-not-admissible')
    data = (folder / 'events.jsonl').read_bytes()
    check(hashlib.sha256(data).hexdigest() == receipt['event_file_sha256'], 'observer-event-file-changed')
    lines = data.splitlines()
    from tools.ms94_b06_observer_audit import MAX_EVENTS
    check(len(lines) == receipt['event_count'] and 2 <= len(lines) <= 50000 + MAX_EVENTS, 'observer-event-count')
    all_records = [json.loads(line) for line in lines]
    check(sum(r['event']['kind'] != 'observer-audit' for r in all_records) <= 50000,
          'observer-evidence-event-count')
    if stub_policy is not None:
        from tools.ms94_b06_forwarding_stub import receipt_records
        check(receipt.get('frame_records') == receipt_records(all_records), 'observer-signed-frame-records-differ')
    if binding_v2 is not None:
        from tools.ms94_b06_observer_v2 import commitments
        check(receipt.get('v2_records') == commitments(all_records), 'observer-v2-receipt-commitments')
    previous, ready, death = None, False, False
    catch_resolution_required = False
    from tools.ms94_b06_observer_audit import Audit, POLICY as AUDIT_POLICY
    structural_audit = Audit()
    audit_required = False
    definitions = {}
    generation_pending = {}
    generation_complete = {}
    stacks, loaders, observations, captures, exceptions = {}, {}, [], [], []
    readbacks, entries, terminals = {}, {}, []
    for sequence, line in enumerate(lines, 1):
        check(len(line) <= 4 * 1024 * 1024, 'observer-event-too-large')
        item = json.loads(line); verify(item)
        check(item['previous_sha256'] == previous, 'observer-event-chain')
        previous = item['content_sha256']; event = item['event']
        check(event['sequence'] == sequence and not death, 'observer-event-order')
        kind = event['kind']
        if kind == 'ready':
            check(sequence == 1 and not ready and event['checkpoint'] is False, 'observer-ready-order')
            if binding_v2 is not None:
                check(event.get('binding_version') == 2, 'observer-v2-collector-version')
            from tools.ms94_b06_generation_catch import POLICY
            catch_policy = event.get('generation_catch_policy')
            check(catch_policy in (None, POLICY), 'observer-generation-catch-policy')
            catch_resolution_required = catch_policy == POLICY
            if binding_v2 is not None:
                binding_v2.catch_resolution_required = catch_resolution_required
            check('unmatched_return_policy' not in event, 'observer-diagnostic-not-admissible')
            ready = True
            check(event.get('audit_policy') in (None, AUDIT_POLICY), 'observer-audit-policy')
            audit_required = event.get('audit_policy') == AUDIT_POLICY
        elif kind == 'observer-audit':
            check(ready and audit_required, 'observer-audit-unannounced')
            structural_audit.event(event)
        elif kind == 'diagnostic-unmatched-return':
            check(False, 'observer-unobserved-generation')
        elif binding_v2 is not None and kind in ('class-definition-v2','generation-entry','generation-return','generation-unwind'):
            check(ready and event['checkpoint'] is False, 'observer-v2-record-order')
            binding_v2.event(event)
        elif kind in ('generation-entry','generation-return','generation-unwind'):
            check(ready and event['checkpoint'] is False,'observer-generation-order')
            record=event['record'];thread=record['thread_id']
            stack=generation_pending.setdefault(thread,[])
            if kind=='generation-entry':stack.append(record)
            else:
                check(bool(stack),'observer-generation-return-without-entry')
                entry=stack.pop()
                check(all(record.get(k)==v for k,v in entry.items()),'observer-generation-entry-return-differs')
                if kind=='generation-unwind':
                    from tools.ms94_b06_generation_catch import validate_unwind
                    validate_unwind(event, catch_resolution_required)
                    continue
                generated=record['returned_class']['class_object_id']
                if 'lambda_factory' in record:generation_complete[generated]=record
        elif kind == 'frame-definition':
            from tools.ms94_b06_forwarding_stub import definition
            check((stub_policy is not None or binding_v2 is not None) and ready and event['checkpoint'] is False, 'observer-definition-order')
            raw = event['definition']
            if binding_v2 is None and 'generation' in raw:
                record=raw['generation']['record']
                check(generation_complete.get(record['returned_class']['class_object_id'])==record,'observer-generation-not-recorded')
            definition(raw)
            check(raw['definition_id'] not in definitions, 'observer-duplicate-definition')
            definitions[raw['definition_id']] = raw
        elif kind == 'vm-death':
            if audit_required: structural_audit.complete()
            check(not any(generation_pending.values()),'observer-generation-incomplete')
            check(ready and sequence == len(lines) and event['checkpoint'] is False and
                  not any(stacks.values()), 'observer-death-with-open-calls')
            death = True
        else:
            check(ready and event['checkpoint'] is True, 'observer-checkpoint-not-suspended')
            frames = (binding_v2.frames(event['frames']) if binding_v2 is not None else
                      checked_frames(event, classes, loaders, definitions, stub_policy, host_entries))
            event = {**event, 'frames':frames}
            if binding_v2 is not None and event.get('catch_location'):
                binding_v2.frames([event['catch_location']])
            if stub_policy is not None and event.get('catch_location'):
                checked_frames({'frames':[event['catch_location']]}, classes, loaders, definitions, stub_policy, host_entries)
            stack = stacks.setdefault(event['thread'], [])
            if kind == 'test-terminal':
                check(frames[0]['class'] == TERMINAL and frames[0]['method'] == 'executionFinished' and
                      frames[0]['signature'] == TERMINAL_SIGNATURE, 'observer-terminal-method')
                check(event['test_class'] == CANDIDATE and event['status'] in ('SUCCESSFUL', 'FAILED', 'ABORTED'),
                      'observer-terminal-test')
                check(not any(f['class'] == SUPPORT or f['class'].startswith(CANDIDATE) for f in frames),
                      'observer-candidate-invoked-terminal')
                check(any(f['class'] == 'org.junit.platform.engine.support.hierarchical.NodeTestTask' for f in frames[1:]),
                      'observer-terminal-engine-stack')
                check(binding_v2 is not None or all(f['class'] in classes or f.get('_verified_forwarding_host') in classes
                          for f in frames if f['class'].startswith('org.junit.')),
                      'observer-terminal-unbound-framework')
                check(not any(t['descriptor_id'] == event['descriptor_id'] for t in terminals),
                      'observer-duplicate-terminal')
                terminals.append(event)
            elif kind == 'method-entry':
                top = frames[0]
                check(top['method'] + top['signature'] in TARGETS.get(top['class'], set()), 'observer-unselected-entry')
                stack.append(event)
                entries[sequence] = event
            elif kind == 'method-exit':
                check(stack and stack[-1]['sequence'] == event['call_sequence'], 'observer-return-without-call')
                entry = stack.pop()
                check(entry['document'] == event['document'] and
                      all(frames[0][k] == entry['frames'][0][k] for k in ('class', 'method', 'signature')),
                      'observer-return-document-or-method')
                observations.append({'entry': entry, 'exit': event, 'origin': origin(entry['frames'])})
            elif kind == 'exception':
                check(event['exception_ancestry'][0] == event['exception_class'] and
                      event['exception_ancestry'][-1] == 'java.lang.Object', 'observer-exception-ancestry')
                for call in event['unwound_calls']:
                    check(stack and stack[-1]['sequence'] == call, 'observer-unwind-without-call')
                    stack.pop()
                exceptions.append(event)
            else:
                check(False, 'observer-unknown-event')
        if event.get('document'):
            check(event['checkpoint'] is True, 'observer-readback-not-suspended')
            capture = read_json(folder / ('readback-%06d.json' % sequence)); verify(capture)
            check(capture['artifact_type'] == 'ms94-b06-posting-native-readback/1' and
                  capture['content_sha256'] == item['readback_sha256'] and capture['lane'] == lane and
                  capture['document'] == event['document'] and capture['event_sequence'] == sequence and
                  capture['read_only'] is True and capture['application_vm_suspended'] is True,
                  'observer-readback-binding')
            queries = queries_for(lane, event['document'])
            check(capture['query_set_sha256'] == digest(queries) and
                  {k: v['sql'] for k, v in capture['results'].items()} == queries, 'observer-readback-query-changed')
            check(capture['results']['health']['rows'] == [{'value': 1}], 'observer-readback-health-failed')
            captures.append(capture['content_sha256'])
            readbacks[sequence] = capture
        else:
            check(item['readback_sha256'] is None, 'observer-unexpected-readback')
    check(ready and death and previous == receipt['last_event_sha256'], 'observer-incomplete-stream')
    return {'entries': entries, 'readbacks': readbacks, 'observations': observations, 'exceptions': exceptions, 'terminals': terminals, 'verified_capture_hashes': captures,
            'event_count': len(lines), 'collection_complete': True,
            **({'observer_v2': binding_v2.finish()} if binding_v2 is not None else {})}


def replay(root, run, lane, public_key):
    root, run = Path(root), Path(run)
    plan = read_json(run / 'plan.json'); verify(plan)
    for name, expected in plan['implementation_sha256'].items():
        bound_file(root, name, expected)
    authorization = read_json(run / 'authorization.json')
    check(verify_envelope(authorization, public_key) and authorization['run_id'] == run.name and
          authorization['scope'] == 'zero-model-native-qualification' and
          authorization['plan']['plan_sha256'] == plan['content_sha256'], 'observer-authorization-binding')
    entry = replay_entry(run, public_key)  # Actually reruns full native admission.
    clocks = replay_clocks(run, public_key)
    spec = plan['posting_observer']
    from tools.ms94_b06_bytecode_policy import validate_jvm
    execution = read_json(run / 'cases/operations/1/execution' / lane / 'execution.json'); verify(execution)
    folder = run / 'posting-observer' / lane
    receipt = read_json(folder / 'receipt.json')
    check(verify_envelope(receipt, public_key) and
          receipt['artifact_type'] == 'ms94-b06-posting-collector-receipt/1' and
          receipt['plan_sha256'] == plan['content_sha256'] and receipt['lane'] == lane and
          receipt['execution_sha256'] == execution['content_sha256'] and receipt['complete'] is True,
          'observer-receipt-invalid')
    validate_jvm(receipt['target']['jvm'], spec)
    if 'built_runtime' in plan:
        from tools.ms94_b06_built_runtime import contract, mount_contract
        manifest,launch,_=contract(root,plan)
        check(receipt['target'].get('readonly_rootfs') is True and
              receipt['target'].get('built_launch_sha256')==launch['content_sha256'] and
              receipt['target'].get('application_mounts')==[list(m) for m in mount_contract(manifest,launch['overlays'])],
              'observer-built-runtime-binding')

    if spec.get('forwarding_stub') is not None:
        from tools.ms94_b06_forwarding_stub import validate_spec
        validate_spec(spec, catalog(root, spec['target_class_files_sha256']))
        entries = receipt.get('host_jar_entries', {})
        check(set(entries) == set(spec['host_jar_entries']), 'observer-host-jar-closure')
        for name, expected in spec['host_jar_entries'].items():
            check(all(entries[name].get(k) == v for k,v in expected.items()) and
                  re.fullmatch('[a-f0-9]{64}', entries[name].get('jar_sha256','')) is not None,
                  'observer-host-jar-binding')
        census = read_json(folder / 'frame-census.json')
        check(verify_envelope(census, public_key) and census['complete'] is True and
              census['plan_sha256'] == plan['content_sha256'] and census['lane'] == lane and
              census['frame_records'] == receipt['frame_records'] and
              census['host_jar_entries'] == entries and census['event_count'] == receipt['event_count'] and
              census['last_event_sha256'] == receipt['last_event_sha256'] and
              census['event_file_sha256'] == receipt['event_file_sha256'], 'observer-census-receipt-binding')
    check(receipt['observer_class_files_sha256'] == spec['class_files_sha256'] and
          receipt['target']['image'] == plan.get('built_runtime', {}).get('image', plan['local']['runner_image']) and
          receipt['target']['ports_published'] is False and
          receipt['target']['observer_private_mount_absent'] is True and
          receipt['target']['jvm']['java_binary_sha256'] == spec['java_binary_sha256'] and
          '-agentlib:jdwp=transport=dt_socket,server=y,suspend=y,address=*:5005' in
          receipt['target']['jvm']['arguments'], 'observer-target-binding')
    binding_v2 = None
    if spec.get('observer_binding_v2') is not None:
        from tools.ms94_b06_observer_v2 import Replay, load_manifest
        manifest, entries = load_manifest(root, spec, receipt['target']['image'])
        check(receipt.get('runtime_files') == manifest['runtime_files'] and
              receipt['target']['jvm']['executable'] == manifest['jdk']['java'], 'observer-v2-runtime-files-differ')
        census = read_json(folder / 'frame-census.json')
        check(verify_envelope(census, public_key) and census['complete'] is True and
              census['plan_sha256'] == plan['content_sha256'] and census['lane'] == lane and
              census['event_file_sha256'] == receipt['event_file_sha256'] and
              census.get('v2_records') == receipt.get('v2_records') and
              census.get('runtime_files') == receipt.get('runtime_files'), 'observer-v2-census-binding')
        binding_v2 = Replay(entries)
    result = replay_stream(folder, receipt, catalog(root, spec['target_class_files_sha256']), lane,
                           spec.get('forwarding_stub'), receipt.get('host_jar_entries', {}), binding_v2)
    return {**result, 'full_entry_replayed': True, 'entry_sha256': entry['content_sha256'],
            'clock': clocks, 'authorization_sha256': authorization['content_sha256'],
            'observer_replayed': True, 'receipt_sha256': receipt['content_sha256'],
            'attribution_qualified': False, 'diagnostics': []}
