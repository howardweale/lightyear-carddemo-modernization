"""Create an unsigned request after the CI plan has been committed. No signing."""
import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess

from tools.prepare_posttran_phase2 import sha, save
from tools.posttran_phase2_authorization import PLAN, REQUEST, check_artifact_metadata


def expiry_status(expires_at, now=None):
    now = now or datetime.now(timezone.utc)
    expiry = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
    return dict(artifact_expires_at=expiry.isoformat(), signing_deadline=(expiry-timedelta(hours=24)).isoformat(),
                warning='Five days or fewer remain before signing deadline' if expiry-timedelta(hours=24)-now <= timedelta(days=5) else None,
                expired=expiry <= now)


def finalize(root, artifact_listing, output, *, now=None):
    root = Path(root)
    at = now or datetime.now(timezone.utc)
    raw = (root/PLAN).read_bytes(); plan = json.loads(raw)
    head = subprocess.check_output(['git','rev-parse','HEAD'], cwd=root, text=True).strip()
    committed = subprocess.check_output(['git','show',head+':'+PLAN], cwd=root)
    if committed != raw: raise ValueError('phase2-plan-must-be-committed')
    from tools.prepare_posttran_phase2 import digest
    if plan.get('schema') != 'posttran-phase2-plan/2' or digest({k:v for k,v in plan.items() if k!='content_sha256'}) != plan['content_sha256']:
        raise ValueError('phase2-fresh-plan-seal')
    listing = json.loads(Path(artifact_listing).read_bytes())
    if listing['total_count'] != len(listing['artifacts']): raise ValueError('phase2-artifact-list-incomplete')
    artifact = check_artifact_metadata(listing['artifacts'], plan, at)
    if artifact.get('workflow_run', {}).get('id') != plan['preparation_run'] or artifact['workflow_run'].get('head_sha') != plan['preparation_head']:
        raise ValueError('phase2-artifact-preparation-binding')
    status = expiry_status(artifact['expires_at'], at)
    request = dict(schema='factory-contract/1', kind='engineering-run-approval', program='POSTTRAN',
        sources=[dict(path=PLAN, sha256=sha(raw), commit=head)],
        details=dict(executable_commit=head, request_seal=plan['content_sha256'],
            observer_sha256=plan['bound_files']['.github/workflows/posttran-phase2.yml'],
            class_hashes=dict(Candidate=plan['candidate_files']['spec/mainframe/posttran-independent/attempt-1/PosttranCandidate.java'],
                Provenance=plan['candidate_files']['spec/mainframe/posttran-independent/attempt-1/provenance.json'],
                CompilerImageArchive=plan['twin']['image_archive_sha256']),
            window=dict(start=at.isoformat(), end=status['signing_deadline']), caps=dict(attempts=1, runs=1)))
    output = Path(output); output.mkdir(parents=True, exist_ok=True)
    save(output/Path(REQUEST).name, request)
    save(output/'posttran-phase2-readiness-2026-10-16.json', dict(schema='posttran-phase2-readiness/1',
        executable_commit=head, preparation_run=plan['preparation_run'], plan_sha256=plan['content_sha256'],
        request_path=REQUEST, artifact_id=artifact['id'], signed=False, effective=False, **status))
    return request


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, default=Path('.')); p.add_argument('--artifacts', required=True)
    p.add_argument('--output', required=True); a=p.parse_args(); finalize(a.root,a.artifacts,a.output)
