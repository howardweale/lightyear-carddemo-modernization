"""Read-only consistency of the unsigned readiness, request and retained compiler."""
import json
from pathlib import Path
from hashlib import sha256
from datetime import datetime, timezone, timedelta
from tools.prepare_posttran_phase2 import digest

FOLDER = 'docs/factory/'
READINESS = FOLDER+'posttran-phase2-readiness-2026-10-17.json'
LEGACY_READINESS = FOLDER+'posttran-phase2-readiness-2026-10-16.json'

def deadline(ready):
    return ready.get('sign_and_launch_by', ready.get('signing_deadline'))


def check(root):
    root=Path(root)
    read=lambda name:json.loads((root/name).read_bytes())
    ready=read(READINESS if (root/READINESS).exists() else LEGACY_READINESS); request=read(ready['request_path'])
    source=next(s for s in request['sources'] if s['path']=='docs/factory/posttran-phase2-plan-2026-10-16.json')
    raw=(root/source['path']).read_bytes();plan=json.loads(raw)
    if sha256(raw).hexdigest()!=source['sha256']:raise ValueError('handoff-plan-file-binding')
    if digest({k:v for k,v in plan.items() if k!='content_sha256'})!=plan['content_sha256']:raise ValueError('handoff-plan-seal')
    if ready['plan_sha256']!=plan['content_sha256'] or request['details']['request_seal']!=ready['plan_sha256']:raise ValueError('handoff-plan-binding')
    if ready['executable_commit']!=request['details']['executable_commit'] or source['commit']!=ready['executable_commit']:raise ValueError('handoff-commit-binding')
    if deadline(ready)!=request['details']['window']['end']:raise ValueError('handoff-deadline-binding')
    metadata=read(FOLDER+'posttran-phase2-artifact-metadata-2026-10-16.json')
    rows=[a for a in metadata['artifacts'] if a['name']==plan['compiler_image_artifact']]
    if len(rows)!=1:raise ValueError('handoff-artifact-count')
    asset=rows[0]
    if asset['id']!=ready['artifact_id'] or asset['workflow_run']['id']!=ready['preparation_run'] or plan['preparation_run']!=ready['preparation_run'] or asset['workflow_run']['head_sha']!=plan['preparation_head']:raise ValueError('handoff-artifact-binding')
    if request['details']['class_hashes']['CompilerImageArchive']!=plan['twin']['image_archive_sha256']:raise ValueError('handoff-archive-binding')
    if datetime.fromisoformat(asset['expires_at'].replace('Z','+00:00'))!=datetime.fromisoformat(ready['artifact_expires_at']):raise ValueError('handoff-expiry-binding')
    if datetime.fromisoformat(deadline(ready))!=datetime.fromisoformat(ready['artifact_expires_at'])-timedelta(hours=24):raise ValueError('handoff-deadline-margin')
    if ready.get('schema') == 'posttran-phase2-readiness/2':
        if sha256((root/FOLDER/'factory-authority.public.pem').read_bytes()).hexdigest() != ready['public_key_sha256']:
            raise ValueError('handoff-public-key-fingerprint')
        if sha256((root/ready['request_path']).read_bytes()).hexdigest() != ready['request_file_sha256']:
            raise ValueError('handoff-request-file-binding')
        check_amendment(root, read(ready['plan_amendment']))
    return ready

def check_amendment(root, amendment):
    root = Path(root)
    original_raw = (root/amendment['original_path']).read_bytes()
    amended_raw = (root/amendment['amended_path']).read_bytes()
    if sha256(original_raw).hexdigest() != amendment['original_file_sha256'] or sha256(amended_raw).hexdigest() != amendment['amended_file_sha256']:
        raise ValueError('handoff-amendment-file-binding')
    original, amended = json.loads(original_raw), json.loads(amended_raw)
    for value, key in ((original, 'original_plan_sha256'), (amended, 'amended_plan_sha256')):
        if value['content_sha256'] != amendment[key] or digest({k:v for k,v in value.items() if k != 'content_sha256'}) != value['content_sha256']:
            raise ValueError('handoff-amendment-seal')
    for row in amendment['amended_fields']:
        if len(row['path']) != 2 or row['path'][0] != 'bound_files':
            raise ValueError('handoff-amendment-field')
        key = row['path'][1]
        if original['bound_files'][key] != row['before'] or amended['bound_files'][key] != row['after']:
            raise ValueError('handoff-amendment-value')
        original['bound_files'][key] = row['after']
    original.pop('content_sha256'); amended.pop('content_sha256')
    if original != amended:
        raise ValueError('handoff-undeclared-plan-amendment')
    return amendment


def timing(ready, now=None):
    now=now or datetime.now(timezone.utc)
    launch_by=datetime.fromisoformat(deadline(ready))
    return dict(evaluated_at=now.isoformat(),days_remaining=round((launch_by-now).total_seconds()/86400,3),warning=now>=launch_by-timedelta(days=5),expired=now>=launch_by)

if __name__=='__main__':print(json.dumps(dict(readiness=check(Path.cwd()),execution_authorized=False)))
