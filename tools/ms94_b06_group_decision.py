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
    verify(group)
    check(re.fullmatch('[a-f0-9]{40}', commit) is not None, 'qualification-public-commit')
    artifacts = {'plan': group, 'snapshot': {'sha256': group['snapshot_sha256']},
                 'window': group['docker_run_window'], 'public_commit': {'commit': commit}}
    bound = {k: hashlib.sha256(canonical(v)).hexdigest() for k,v in artifacts.items()}
    evidence = {k: 'evidence/b06/qualification/'+v+'.json' for k,v in bound.items()}
    value = {'schema': 'tower-request/1', 'scope': SCOPE, 'kind': KIND,
             'bound': bound, 'evidence': evidence, 'proposed_by': 'b06-qualification-controller',
             'summary': 'Authorize one zero-model qualification group in its exact Docker window. Operator review; not independent attestation.'}
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
