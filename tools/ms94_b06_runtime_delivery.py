"""Authenticated terminal exception -> closed diagnostic -> recorded zero-model inbox.

No model transport. Exception prose, SQL and document identities never enter the
closed payload. A terminal JUnit result must name the actual observed throwable.
"""
import hashlib
import re
from pathlib import Path

from lightyear_calibration.contracts import canonical, read_json, verify
from lightyear_control_tower.decisions import verify_envelope
from tools.ms94_b06_admission import check, bound_file, sign_once
from tools.ms94_b06_posting_replay import CANDIDATE, SUPPORT, replay
from tools.qualification_feedback_v4 import EXCEPTIONS, PACKAGES, masked_source

POLICY = 'docs/calibration/idempiere-ms94/stage-b-06/preparation/template-r1/diagnostic-policy.json'


def terminal_projection(stream, execution, source):
    """Pure replay after authentication; synthetic unit inputs confer no admission."""
    check(stream['collection_complete'], 'runtime-incomplete-collection')
    terminals = stream.get('terminals', [])
    if execution['exit_code'] == 0:
        check(terminals and all(t['status'] == 'SUCCESSFUL' and t['exception_id'] is None for t in terminals),
              'runtime-success-terminal-mismatch')
        return None, False
    failed = [t for t in terminals if t['status'] == 'FAILED']
    if len(failed) != 1 or any(t['status'] == 'ABORTED' for t in terminals):
        return None, True
    terminal = failed[0]
    roots = [e for e in stream['exceptions'] if e.get('exception_id') == terminal['exception_id']
             and e['sequence'] < terminal['sequence'] and e['thread'] == terminal['thread']]
    if not roots:
        return None, True
    # Re-throws may repeat the same object; origin is its first observed throw.
    event = min(roots, key=lambda e: e['sequence'])
    if any(any(c.startswith(('java.sql.', 'org.postgresql.', 'oracle.jdbc.')) or
               c in ('java.lang.VirtualMachineError', 'java.lang.LinkageError')
               for c in e['exception_ancestry']) for e in stream['exceptions']):
        return None, True
    frame = None
    for f in event['frames']:
        name = f['class']
        if name == CANDIDATE or name.startswith(CANDIDATE + '$'):
            frame = f; break
        if not name.startswith(('java.', 'org.junit.', 'org.opentest4j.', 'junit.framework.')):
            return None, True  # includes support, application and unknown helpers
    if frame is None:
        return None, True
    masked = masked_source(source)
    boundary = re.search(r'\b(?:final\s+)?class\s+JourneySupport\b', masked)
    check(boundary is not None, 'runtime-source-support-boundary-missing')
    candidate_text = masked[:boundary.start()]
    line, method = frame.get('line'), frame['method']
    check(type(line) is int and 0 < line <= candidate_text.count('\n') + 1 and
          re.fullmatch(r'[A-Za-z_$][A-Za-z0-9_$]{0,127}', method) is not None,
          'runtime-candidate-frame-invalid')
    declared = method.split('$')[1] if method.startswith('lambda$') else method
    check(re.search(r'\b' + re.escape(declared) + r'\s*\(', candidate_text) is not None,
          'runtime-frame-not-in-bound-source')
    simple = event['exception_class'].rsplit('.', 1)[-1]
    label = simple if simple in EXCEPTIONS and event['exception_class'].startswith(PACKAGES) else 'other'
    return {'category': 'candidate-runtime-exception', 'exception_class': label,
            'thrown_by': 'candidate', 'candidate_frame': {'method': method, 'line': line}}, False


def project_pair(root, run, public_key):
    root, run = Path(root), Path(run)
    plan = read_json(run / 'plan.json'); verify(plan)
    bound_file(root, POLICY, plan['runtime_delivery']['policy_sha256'])
    policy = read_json(root / POLICY)
    check('candidate-runtime-exception' in policy['direct_categories'] and
          policy['runtime_origin_required'] == 'candidate', 'runtime-policy-direct-route-missing')
    source = bound_file(run / 'inputs', 'operations.java', plan['harness_sha256']).read_text(encoding='utf-8')
    values, bindings, suspects = [], {}, []
    for lane in ('oracle', 'postgresql'):
        stream = replay(root, run, lane, public_key)
        execution = read_json(run / 'cases/operations/1/execution' / lane / 'execution.json'); verify(execution)
        value, suspect = terminal_projection(stream, execution, source)
        bindings[lane] = {'entry_sha256': stream['entry_sha256'], 'clock': stream['clock'],
                          'collector_receipt_sha256': stream['receipt_sha256'],
                          'execution_sha256': execution['content_sha256']}
        if suspect: suspects.append(lane)
        if value: values.append(value)
    output = []
    if not suspects:
        for value in values:
            if not any(
                    {k: v for k, v in d.items() if k not in ('id', 'lanes')} == value for d in output):
                output.append({'id': 'runtime-' + str(len(output) + 1), **value,
                               'lanes': 'both' if values.count(value) == 2 else 'one'})
    posting = {}
    if plan.get('slot_kind') == 'posting-origin':
        from tools.ms94_b06_posting_cause import replay_cause
        from tools.ms94_b06_posting_delivery import native_label, project
        from tools.ms94_b06_admission import native_pair_tables
        causes = {lane: replay_cause(root, run, lane, public_key) for lane in ('oracle','postgresql')}
        labels = {}
        if all(c['cause'] == 'candidate-prior-processing-flag' and not c['equipment_suspect'] for c in causes.values()):
            before, after, captures = native_pair_tables(run)
            labels = {lane: native_label(plan['journey'], causes[lane]['document_key'], before[lane], after[lane])
                      for lane in causes}
            posting['label_capture_bindings'] = captures
        output, suspect = project(causes, labels, policy)
        suspects = ['posting-origin'] if suspect else []
        posting.update(posting_causes=causes, posting_control_replayed=True)
    return {'artifact_type': 'ms94-b06-runtime-projection/1', 'plan_sha256': plan['content_sha256'],
            'policy_sha256': plan['runtime_delivery']['policy_sha256'], 'native_bindings': bindings,
            'diagnostics': output, 'equipment_suspect': bool(suspects),
            'route': 'halt-equipment-suspect' if suspects else 'direct-builder' if output else 'none',
            'model_calls': 0, **posting}


def route(diagnostics, policy, *, equipment_suspect):
    """Legacy categories still require analyst selection; direct ones do not."""
    if equipment_suspect:
        return {'direct': [], 'analyst': [], 'halt': True}
    direct, legacy = [], []
    for value in diagnostics:
        if value['category'] in policy['direct_categories']:
            check(value['category'] != 'candidate-runtime-exception' or value['thrown_by'] == 'candidate',
                  'runtime-noncandidate-direct-route')
            direct.append(value)
        else:
            legacy.append(value)
    return {'direct': direct, 'analyst': legacy, 'halt': False}


def record_zero_model_delivery(root, run, signer):
    """The inbox is really written and consumed; no fictional builder invocation."""
    run = Path(run)
    plan = read_json(run / 'plan.json')
    check(plan['model_calls'] == 0 and plan['qualification_only'] is True and
          plan['runtime_delivery']['consumer'] == 'zero-model-preflight-inbox/1', 'runtime-not-zero-model-inbox')
    value = project_pair(root, run, signer.public)
    projected = sign_once(run / 'runtime-diagnostic.json', value, signer)
    payload = canonical(value['diagnostics'])
    payload_sha = hashlib.sha256(payload).hexdigest()
    delivered = value['route'] == 'direct-builder'
    if delivered:
        inbox = run / 'zero-model-builder-inbox.json'
        sign_once(inbox, {'artifact_type': 'ms94-b06-zero-model-builder-inbox/1',
                  'plan_sha256': plan['content_sha256'], 'projection_sha256': projected['content_sha256'],
                  'payload_sha256': payload_sha, 'diagnostics': value['diagnostics'], 'model_calls': 0}, signer)
        received = read_json(inbox)
        check(verify_envelope(received, signer.public) and canonical(received['diagnostics']) == payload,
              'runtime-inbox-delivery-differs')
    return sign_once(run / 'runtime-delivery.json', {
        'artifact_type': 'ms94-b06-zero-model-delivery/1', 'plan_sha256': plan['content_sha256'],
        'projection_sha256': projected['content_sha256'], 'payload_sha256': payload_sha,
        'inbox_sha256': read_json(run / 'zero-model-builder-inbox.json')['content_sha256'] if delivered else None,
        'delivered': delivered, 'analyst_invocations': 0, 'model_calls': 0,
        'equipment_suspect': value['equipment_suspect'], 'route': value['route'],
        'consumer': 'zero-model-preflight-inbox/1', 'native_qualification': False,
    }, signer)


def replay_delivery(root, run, public_key):
    run = Path(run)
    expected = project_pair(root, run, public_key)
    projection = read_json(run / 'runtime-diagnostic.json')
    record = read_json(run / 'runtime-delivery.json')
    check(verify_envelope(projection, public_key) and verify_envelope(record, public_key), 'runtime-delivery-signature')
    check(all(projection.get(k) == v for k, v in expected.items()), 'runtime-projection-replay-differs')
    payload = canonical(expected['diagnostics'])
    delivered = expected['route'] == 'direct-builder'
    check(record['projection_sha256'] == projection['content_sha256'] and
          record['plan_sha256'] == expected['plan_sha256'] and record['delivered'] == delivered and
          record['payload_sha256'] == hashlib.sha256(payload).hexdigest() and
          record['route'] == expected['route'] and record['equipment_suspect'] == expected['equipment_suspect'] and
          record['model_calls'] == record['analyst_invocations'] == 0 and
          record['consumer'] == 'zero-model-preflight-inbox/1', 'runtime-delivery-replay-differs')
    inbox = run / 'zero-model-builder-inbox.json'
    if delivered:
        received = read_json(inbox)
        check(verify_envelope(received, public_key) and received['content_sha256'] == record['inbox_sha256'] and
              received['plan_sha256'] == expected['plan_sha256'] and
              received['projection_sha256'] == projection['content_sha256'] and
              received['payload_sha256'] == record['payload_sha256'] and
              received['model_calls'] == 0 and canonical(received['diagnostics']) == payload, 'runtime-inbox-replay-differs')
    else:
        check(not inbox.exists() and record['inbox_sha256'] is None, 'runtime-unexpected-delivery')
    return {'runtime_origin_replayed': True, 'diagnostic_replayed': True,
            'delivery_replayed': True, 'delivered': delivered, 'equipment_suspect': expected['equipment_suspect'],
            'delivery_sha256': record['content_sha256'], 'model_calls': 0}
