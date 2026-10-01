"""Replay the qualified entry boundary and closed feedback; measure actual delivery."""
import hashlib
from lightyear_calibration.contracts import canonical, read_json, require, verify
from lightyear_control_tower.decisions import verify_envelope
from tools.ms94_a3_entry import check
from tools.qualification_feedback_v4 import export, equipment_suspect


def projection(root, run):
    declaration = read_json(root/'factory/idempiere/qualification-ms94-v3/public/operations.json')
    api = read_json(root/'factory/idempiere/analyst-repair/api-provenance.json')
    diagnostics = export(run, declaration, root=root, api=api)
    suspect = equipment_suspect(run, declaration, root=root, api=api)
    require(not suspect or not diagnostics, 'Equipment-suspect feedback must be empty')
    return {'diagnostics': diagnostics, 'equipment_suspect': suspect,
            'disposition': 'halted-equipment-suspect' if suspect else 'measured-candidate',
            'diagnostic_bytes_sha256': hashlib.sha256(canonical(diagnostics)).hexdigest(),
            'gate_sha256': read_json(run/'gate.json')['content_sha256'],
            'candidate_sha256': read_json(run/'plan.json')['harness_sha256']}


def verify_attempt(root, run, key):
    plan = read_json(run/'plan.json'); verify(plan)
    native = read_json(run/'receipt.json')
    require(verify_envelope(native, key) and native['plan_sha256'] == plan['content_sha256'],
            'Native receipt/plan binding differs')
    cleanup = read_json(run/'cleanup.json')
    require(verify_envelope(cleanup, key) and cleanup['complete'] and native['cleanup_complete'],
            'Incomplete signed native cleanup')
    entry = read_json(run/'a3-entry-admission.json')
    require(verify_envelope(entry, key), 'Invalid full entry signature')
    checked = check(run)
    require(all(entry.get(k) == v for k, v in checked.items() if k != 'content_sha256'),
            'Full entry replay differs')
    recorded = read_json(run/'diagnostic-projection.json')
    require(verify_envelope(recorded, key) and
            recorded['content_sha256'] == native['diagnostic_projection_sha256'], 'Projection binding differs')
    actual = projection(root, run)
    require({k:v for k,v in recorded.items() if k not in ('signature','content_sha256')} == actual,
            'Diagnostic bytes, suspicion or disposition differ')
    return {'full_entry_replayed': True, 'diagnostic_replayed': True,
            'diagnostic_bytes_sha256': actual['diagnostic_bytes_sha256'],
            'equipment_suspect': actual['equipment_suspect']}


def metrics(root, campaign, attempts):
    builders = [p.parent for p in sorted((campaign/'calls').glob('*/invocation.json'))
                if read_json(p)['role'] == 'builder']
    records = [r for p in (campaign/'calls').glob('*/tool-transcript.json') for r in read_json(p)]
    rows = []
    for i, attempt in enumerate(attempts, 1):
        exported = campaign/f'analyst-input-{i}.json'
        diagnostics = read_json(exported)['diagnostics'] if exported.exists() else []
        feedback = campaign/f'feedback-{i}.json'
        selected = read_json(feedback)['diagnostics'] if feedback.exists() else []
        # A saved selection alone is not delivery. Require the next builder invocation's prompt.
        sent = (i < len(builders) and bool(selected) and
                read_json(builders[i]/'prompt.json').get('analyst_feedback') == selected)
        native = read_json(root/attempt['run_directory']/'receipt.json')
        rows.append({'attempt': i, 'result_class': attempt['result_class'],
                     'diagnostic_exported': bool(diagnostics), 'diagnostic_sent': sent,
                     'equipment_suspect': native.get('equipment_suspect', False)})
    eligible = bool(rows and rows[0]['result_class'] == 'execution-failure' and rows[0]['diagnostic_sent'])
    return {'attempts': rows, 'repair_conversion_eligible': eligible,
            'compilations': sum(r['invocation']['tool'] == 'compile' and
                                r['result']['output'].get('status') != 'tool-rejected' for r in records),
            'execution_failures': sum(r['result_class'] == 'execution-failure' for r in rows),
            'execution_failures_with_diagnostic_sent': sum(r['result_class'] == 'execution-failure' and
                                                            r['diagnostic_sent'] for r in rows),
            'execution_failures_with_diagnostic_exported': sum(r['result_class'] == 'execution-failure' and
                                                                r['diagnostic_exported'] for r in rows),
            'post_repair_business_failures': sum(r['attempt'] > 1 and r['result_class'] == 'business-failure' for r in rows)}
