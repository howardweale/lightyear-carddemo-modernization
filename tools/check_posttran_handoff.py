"""Read-only consistency of the unsigned readiness, request and retained compiler."""
import json
from pathlib import Path
from hashlib import sha256
from datetime import datetime, timezone, timedelta
from tools.prepare_posttran_phase2 import digest

FOLDER = 'docs/factory/'
READINESS = FOLDER+'posttran-phase2-readiness-2026-10-16.json'

def check(root):
    root=Path(root)
    read=lambda name:json.loads((root/name).read_bytes())
    ready=read(READINESS); request=read(ready['request_path'])
    source=next(s for s in request['sources'] if s['path']=='docs/factory/posttran-phase2-plan-2026-10-16.json')
    raw=(root/source['path']).read_bytes();plan=json.loads(raw)
    if sha256(raw).hexdigest()!=source['sha256']:raise ValueError('handoff-plan-file-binding')
    if digest({k:v for k,v in plan.items() if k!='content_sha256'})!=plan['content_sha256']:raise ValueError('handoff-plan-seal')
    if ready['plan_sha256']!=plan['content_sha256'] or request['details']['request_seal']!=ready['plan_sha256']:raise ValueError('handoff-plan-binding')
    if ready['executable_commit']!=request['details']['executable_commit'] or source['commit']!=ready['executable_commit']:raise ValueError('handoff-commit-binding')
    if ready['signing_deadline']!=request['details']['window']['end']:raise ValueError('handoff-deadline-binding')
    metadata=read(FOLDER+'posttran-phase2-artifact-metadata-2026-10-16.json')
    rows=[a for a in metadata['artifacts'] if a['name']==plan['compiler_image_artifact']]
    if len(rows)!=1:raise ValueError('handoff-artifact-count')
    asset=rows[0]
    if asset['id']!=ready['artifact_id'] or asset['workflow_run']['id']!=ready['preparation_run'] or plan['preparation_run']!=ready['preparation_run'] or asset['workflow_run']['head_sha']!=plan['preparation_head']:raise ValueError('handoff-artifact-binding')
    if request['details']['class_hashes']['CompilerImageArchive']!=plan['twin']['image_archive_sha256']:raise ValueError('handoff-archive-binding')
    if datetime.fromisoformat(asset['expires_at'].replace('Z','+00:00'))!=datetime.fromisoformat(ready['artifact_expires_at']):raise ValueError('handoff-expiry-binding')
    if datetime.fromisoformat(ready['signing_deadline'])!=datetime.fromisoformat(ready['artifact_expires_at'])-timedelta(hours=24):raise ValueError('handoff-deadline-margin')
    return ready

def timing(ready, now=None):
    now=now or datetime.now(timezone.utc)
    deadline=datetime.fromisoformat(ready['signing_deadline'])
    return dict(evaluated_at=now.isoformat(),days_remaining=round((deadline-now).total_seconds()/86400,3),warning=now>=deadline-timedelta(days=5),expired=now>=deadline)

if __name__=='__main__':print(json.dumps(dict(readiness=check(Path.cwd()),execution_authorized=False)))
