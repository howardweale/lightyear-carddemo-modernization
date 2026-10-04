"""Offline replay of external JVM checkpoints and native SQL readbacks.

This verifies collection, not causal attribution or qualification. In particular,
a signed assertion that an equipment fault was absent is never sufficient.
"""
import hashlib
import json
from pathlib import Path

from lightyear_calibration.contracts import read_json, verify, digest
from lightyear_calibration.b06_posting_probe import queries_for
from lightyear_control_tower.decisions import verify_envelope
from tools.ms94_b06_admission import check, bound_file, replay_entry, replay_clocks
from tools.ms94_b06_classfile import inspect_class

SUPPORT = 'org.idempiere.test.JourneySupport'
CANDIDATE = 'org.idempiere.test.LightyearOperationsTest'
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
        item = inspect_class(bound_file(root, name, expected).read_bytes())
        check(item['class'] not in result, 'observer-duplicate-class-identity')
        result[item['class']] = item
    check({SUPPORT, CANDIDATE, *FRAMEWORK} <= set(result), 'observer-class-catalog-incomplete')
    return result


def checked_frames(event, classes, loaders):
    frames = event['frames']
    check(isinstance(frames, list) and frames, 'observer-stack-empty')
    for frame in frames:
        name = frame['class']
        if name in classes or name == SUPPORT or name.startswith(CANDIDATE) or name in FRAMEWORK:
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
        name = frame['class']
        if name in FRAMEWORK:
            continue
        if name == SUPPORT:
            return 'support'
        if name == CANDIDATE or name.startswith(CANDIDATE + '$'):
            return 'candidate'
        return 'outside'
    return 'outside'


def replay_stream(folder, receipt, classes, lane):
    """Pure content verification; caller must authenticate receipt and full entry."""
    data = (folder / 'events.jsonl').read_bytes()
    check(hashlib.sha256(data).hexdigest() == receipt['event_file_sha256'], 'observer-event-file-changed')
    lines = data.splitlines()
    check(len(lines) == receipt['event_count'] and 2 <= len(lines) <= 50000, 'observer-event-count')
    previous, ready, death = None, False, False
    stacks, loaders, observations, captures, exceptions = {}, {}, [], [], []
    readbacks, entries = {}, {}
    for sequence, line in enumerate(lines, 1):
        check(len(line) <= 4 * 1024 * 1024, 'observer-event-too-large')
        item = json.loads(line); verify(item)
        check(item['previous_sha256'] == previous, 'observer-event-chain')
        previous = item['content_sha256']; event = item['event']
        check(event['sequence'] == sequence and not death, 'observer-event-order')
        kind = event['kind']
        if kind == 'ready':
            check(sequence == 1 and not ready and event['checkpoint'] is False, 'observer-ready-order')
            ready = True
        elif kind == 'vm-death':
            check(ready and sequence == len(lines) and event['checkpoint'] is False and
                  not any(stacks.values()), 'observer-death-with-open-calls')
            death = True
        else:
            check(ready and event['checkpoint'] is True, 'observer-checkpoint-not-suspended')
            frames = checked_frames(event, classes, loaders)
            stack = stacks.setdefault(event['thread'], [])
            if kind == 'method-entry':
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
    return {'entries': entries, 'readbacks': readbacks, 'observations': observations, 'exceptions': exceptions, 'verified_capture_hashes': captures,
            'event_count': len(lines), 'collection_complete': True}


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
    execution = read_json(run / 'cases/operations/1/execution' / lane / 'execution.json'); verify(execution)
    folder = run / 'posting-observer' / lane
    receipt = read_json(folder / 'receipt.json')
    check(verify_envelope(receipt, public_key) and
          receipt['artifact_type'] == 'ms94-b06-posting-collector-receipt/1' and
          receipt['plan_sha256'] == plan['content_sha256'] and receipt['lane'] == lane and
          receipt['execution_sha256'] == execution['content_sha256'] and receipt['complete'] is True,
          'observer-receipt-invalid')
    check(receipt['observer_class_files_sha256'] == spec['class_files_sha256'] and
          receipt['target']['image'] == plan['local']['runner_image'] and
          receipt['target']['ports_published'] is False and
          receipt['target']['observer_private_mount_absent'] is True and
          receipt['target']['jvm']['java_binary_sha256'] == spec['java_binary_sha256'] and
          '-agentlib:jdwp=transport=dt_socket,server=y,suspend=y,address=*:5005' in
          receipt['target']['jvm']['arguments'], 'observer-target-binding')
    result = replay_stream(folder, receipt, catalog(root, spec['target_class_files_sha256']), lane)
    return {**result, 'full_entry_replayed': True, 'entry_sha256': entry['content_sha256'],
            'clock': clocks, 'authorization_sha256': authorization['content_sha256'],
            'observer_replayed': True, 'receipt_sha256': receipt['content_sha256'],
            'attribution_qualified': False, 'diagnostics': []}
