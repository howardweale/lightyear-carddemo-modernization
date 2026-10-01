"""Admit only the reviewed B03 classification and exact independently verified equipment."""
from pathlib import Path
from lightyear_calibration.contracts import read_json, require, verify
from lightyear_calibration.journey_order import file_hash
from lightyear_control_tower.decisions import verify_envelope
from tools.ms94_stage_b_admission_v5 import stage_a as previous_stage_a

AREA = Path('docs/calibration/idempiere-ms94/equipment-06')
PINS = {'stage-a1': {'plan.json': 'd41071031ad88e9ecf93d14b0d3cdc373d5835ee13a05e81cc490e8eeb56294e', 'report.json': 'd9e07b193e55cddd64c7a170ab259694eac6be9b1dc99ac05de95bf3af77f399', 'terminal-verification.json': '2eb0dfe4793bea8e43257cbf6a54799a177ce111fe79ce1bda54370e7222598d'}, 'stage-a2-r1': {'plan.json': 'fdfc44c22c9808e20c877d4f5a59d2e18ab3fe1228e2c07342e9fb3d95c7edae', 'report.json': '739e407287fa85093c28d6221f1b2449a4856e1c02cb8d749109fcf4cd24e684', 'terminal-verification.json': 'c1e75a2a25d1647420c16c1dfcce68fc11d8e56f108219c31499925821edbeea'}, 'stage-a3-checkpoint-r1': {'plan.json': '70514d96b90155321142dab7f318e64cc0fdbfdfc36d76701cccf677c7cab1a8', 'report.json': '2dd8e1acbe98767cfc052dd56df2e3b12e2824b0be227e1fd1d731f0c2e9aceb', 'terminal-verification.json': '9bf52b816897f351e6a8261abae0b590aa184309d2d1c1859ba6b33a9ab0711f'}, 'stage-dated-controls': {'plan.json': '1b8ba33a2714317ee8b9ef1fb7989216a1a7d96e744bdbaa777b979cb791169a', 'report.json': 'fc66d4b95b1f85557b4c33f77141fd5612540f38e6590cb3e98380af8a72a2bf', 'terminal-verification.json': 'f25c05966a99956b07d4480a4b6bdb789d675e67723e73f56753ff1953dbcbbb'}, 'stage-a3-dated': {'plan.json': '778ced58c7d64e75ece1b5b66958423324230c8110e90546ac55e6d6e40fa7c3', 'report.json': '64c622f7c747b2d0084e43a8ed942c61d24f5f6fa146be9251a5fc4504b3ea8b', 'terminal-verification.json': '4240dd663aafdae20c9580addbf5744b76376e7f0763bb41ad28c870086386a9'}}


def prerequisites(root):
    root = Path(root); key = (root/'work/ms87/operator/authority.public.pem').read_bytes()
    for stage, pins in PINS.items():
        values = {name: read_json(root/AREA/stage/name) for name in pins}
        for name, value in values.items():
            if name == 'plan.json': verify(value)
            require(value['content_sha256'] == pins[name], 'Wrong prerequisite: '+stage+'/'+name)
            if name != 'plan.json': require(verify_envelope(value,key), 'Invalid prerequisite signature')
        plan, report, audit = [values[n] for n in ('plan.json','report.json','terminal-verification.json')]
        require(report['passed'] and report['error'] is None and report['model_calls'] == 0
                and report['plan_sha256'] == plan['content_sha256']
                and audit['report_sha256'] == report['content_sha256'] and audit['cleanup_verified'],
                'Incomplete prerequisite')
        for name, digest in plan.get('implementation_sha256',{}).items():
            require(file_hash(root/name) == digest, 'Qualified equipment changed: '+name)
        if stage in ('stage-dated-controls','stage-a3-dated'):
            count = 28 if stage == 'stage-dated-controls' else 14
            require(len(report['results']) == count and len(audit['publications']) == count
                    and audit['passed'] and audit['all_available_archives_replayed']
                    and all(all(p[k] for k in ('verified','full_entry_replayed','complete_gate_replayed','diagnostic_replayed'))
                            for p in audit['publications']), 'Incomplete dated source or paired replay')
        if stage == 'stage-a3-dated':
            require(len(report['comparisons']) == 7 and all(c['diagnostic_bytes_equal'] for c in report['comparisons'])
                    and audit['paired_diagnostic_bytes_suspicion_dispositions_equal'], 'Paired leak qualification failed')
    b03 = root/'docs/calibration/idempiere-ms94/stage-b-03'
    classification = read_json(b03/'classification.json')
    classification_hash = file_hash(b03/'classification.json')
    review = read_json(b03/'operator-adjudication.json')
    require(classification_hash == 'b1bcd5f20729f1b5ac9893825e8e61f10c7df49e4a1a955f2910441fbe70262c'
            and review['classification_sha256'] == classification_hash
            and review['accepted_decisions'] == [1,2,3,4] and review['review_mode'] == 'operator review'
            and review['b04_classification_prerequisite_satisfied'], 'B03 operator review incomplete')
    return {'qualification': PINS, 'classification_sha256': classification_hash,
            'operator_adjudication_file_sha256': file_hash(b03/'operator-adjudication.json'),
            'review_mode': 'operator review; not independent human attestation',
            'checkpoint_verification_sha256': PINS['stage-a3-checkpoint-r1']['terminal-verification.json']}


def stage_a(root, equipment, live=False):
    base, acceptance = previous_stage_a(root, equipment, live=live)
    prerequisites(root)
    return base, acceptance


def public_freeze(root, output, plan, key):
    """The signed publication receipt is created only after remote byte verification."""
    receipt = read_json(output/'published-plan.json')
    require(verify_envelope(receipt, key) and receipt['plan_sha256'] == plan['content_sha256']
            and receipt['remote_verified'] and receipt['all_remote_bytes_verified']
            and receipt['public_before_generation'] and len(receipt['commit']) == 40,
            'Exact public B04 freeze missing')
    required = {'execution-snapshot.json', (output/'plan.json').relative_to(root).as_posix(),
                (output/'declaration.json').relative_to(root).as_posix(),
                'factory/idempiere/qualification-ms94-v8/b04-diagnostic-allowlists.json'}
    for slot in plan['slots']:
        required.update(slot['path']+'/'+n for n in ('plan.json','declaration.json'))
    require(required == set(receipt['files']), 'Incomplete public B04 plan/declaration/allowlist publication')
    for name, digest in receipt['files'].items():
        require(file_hash(root/name) == digest, 'Publicly frozen B04 bytes changed: '+name)
    snapshot = read_json(root/'execution-snapshot.json'); verify(snapshot)
    require(receipt['snapshot_sha256'] == snapshot['content_sha256'], 'Public snapshot binding differs')
    return receipt
