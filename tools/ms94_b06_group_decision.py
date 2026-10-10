"""Operator authorization from a fresh Tower journal, separate from campaign keys."""
import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path
from lightyear_calibration.contracts import canonical, digest, verify
from lightyear_control_tower.b06 import SCOPE, atomic_new
from lightyear_control_tower.verification import verify_decision
from tools.ms94_b06_admission import check, utc

KIND = 'b06-qualification-group'


def request(group, commit):
    """Deterministic review request; hashes cover exact reviewed JSON bytes."""
    from tools.ms94_b06_engineering_boundary import refuse_engineering
    refuse_engineering(group)
    verify(group)
    check(re.fullmatch('[a-f0-9]{40}', commit) is not None, 'qualification-public-commit')
    artifacts = {'plan': group, 'snapshot': {'sha256': group['snapshot_sha256']},
                 'window': group['docker_run_window'], 'public_commit': {'commit': commit}}
    bound = {k: hashlib.sha256(canonical(v)).hexdigest() for k,v in artifacts.items()}
    evidence = {k: 'evidence/b06/qualification/'+v+'.json' for k,v in bound.items()}
    value = {'schema': 'tower-request/1', 'scope': SCOPE, 'kind': KIND,
             'bound': bound, 'evidence': evidence, 'proposed_by': 'b06-qualification-controller',
             'summary': 'Authorize one zero-model qualification group in its exact Docker window. Operator review; not independent attestation.'}
    if group.get('purpose') == 'five-path-provenance-census':
        check(group.get('qualification_credit') is False, 'census-not-qualification-credit')
        value['summary'] = ('Authorize five serial zero-model provenance-census pairs: three J1 paths, '
                            'J2 reference and J3 reference. No qualification or measurement credit. '
                            'Exact Docker window; operator review, not independent attestation.')
    if group.get('purpose') == 'observer-native-practice':
        check(group.get('qualification_credit') is False and group.get('slot_count') == 1 and
              group.get('journey') == 'J1', 'practice-scope')
        value['summary'] = ('Authorize one fresh zero-model J1 retained-reference practice pair '
                            '(Oracle and PostgreSQL), using the corrected external observer. '
                            'No retries, qualification or measurement credit. Exact Docker window; '
                            'operator review, not independent attestation.')
        if 'diagnostic_scope' in group:
            scope = group['diagnostic_scope']
            check(scope.get('purpose') == 'capture-refusal-context-only' and
                  scope.get('qualification_credit') is False and scope.get('measurement_credit') is False and
                  scope.get('stop_at_first_anomaly') is True and scope.get('degradation_mode') is False and
                  scope.get('automatic_retry') is False and scope.get('minimum_full_plan_review_lead_seconds') == 14400 and
                  group.get('model_calls') == 0 and group.get('measurement_authorized') is False,
                  'diagnostic-capture-only-scope')
            value['summary'] = ('Authorize ONE diagnostic J1 retained-reference pair solely to capture observer refusal context. '
                                'Strict stop at first anomaly; no degradation or retries. Zero models, qualification or measurement credit. '
                                'Full frozen plan requires four hours of review lead before latest start and explicit Docker approval. '
                                'Captured failure requires offline reproduction and a proven fix before qualification. '
                                'Operator review; not independent attestation.')
    value['id'] = 'b06-q-'+digest(value)
    return value, {**bound, 'request': digest(value)}, artifacts


def write_request(root, group, commit):
    value, bound, artifacts = request(group, commit)
    for name, artifact in artifacts.items():
        path = Path(root)/value['evidence'][name]
        if path.exists():
            check(path.read_bytes() == canonical(artifact), 'qualification-review-evidence-changed')
        else:
            atomic_new(path, artifact)
    path = Path(root)/'work/control-tower/requests'/SCOPE/(value['id']+'.json')
    if path.exists():
        check(path.read_bytes() == canonical(value), 'qualification-request-changed')
    else:
        atomic_new(path, value)
    return value['id'], bound


def authorize(group, commit, reader, campaign_key, now=None):
    """Reader obtains current authenticated Tower history; files are not authority."""
    now = now or datetime.now(timezone.utc)
    check(reader is not None, 'qualification-tower-reader-required')
    check(reader.key != campaign_key and hashlib.sha256(reader.key).hexdigest() ==
          group['tower_public_key_sha256'], 'qualification-tower-trust-binding')
    _, bound, _ = request(group, commit)
    proof = reader.get(KIND, bound, now)
    check(proof is not None, 'qualification-tower-decision-required')
    journal = proof['journal']
    check(abs((now-utc(journal['exported_at'])).total_seconds()) < 60, 'qualification-tower-history-stale')
    verify_decision(proof, reader.key, KIND, bound, scope=SCOPE,
                    expected_head=journal['journal_head_sha256'], outcomes={'authorized'}, now=now)
    return proof
