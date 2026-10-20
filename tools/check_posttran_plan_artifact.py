"""Verify the original CI plan or its retained bytes after artifact expiry."""
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import subprocess
import zipfile
from tools.check_posttran_handoff import check_amendment


def provenance(metadata, amendment):
    if (metadata['id'] != amendment['artifact_id'] or metadata['name'] != 'posttran-phase2-plan'
            or metadata['workflow_run']['id'] != amendment['preparation_run']
            or metadata['workflow_run']['head_sha'] != amendment['preparation_head']):
        raise ValueError('handoff-original-artifact-provenance')


def verify(root, *, now=None, repository=None, run=None):
    root=Path(root); run=run or subprocess.check_output
    now=now or datetime.now(timezone.utc)
    repository=repository or os.environ.get('GITHUB_REPOSITORY')
    if not repository or len(repository.split('/')) != 2:
        raise ValueError('handoff-repository-required')
    amendment=json.loads((root/'docs/factory/posttran-phase2-plan-amendment-2026-10-17.json').read_bytes())
    retained=json.loads((root/'docs/factory/posttran-phase2-artifact-metadata-2026-10-16.json').read_bytes())
    matches=[r for r in retained['artifacts'] if r['id']==amendment['artifact_id']]
    if len(matches)!=1: raise ValueError('handoff-retained-artifact-count')
    provenance(matches[0],amendment)
    check_amendment(root,amendment)
    expired=now >= datetime.fromisoformat(matches[0]['expires_at'].replace('Z','+00:00'))
    path='committed-original-and-amendment' if expired else 'live-ci-artifact'
    if not expired:
        prefix='repos/'+repository+'/actions/artifacts/'+str(amendment['artifact_id'])
        metadata=json.loads(run(['gh','api',prefix]))
        provenance(metadata,amendment)
        if metadata['expired']: raise ValueError('handoff-artifact-expired-before-retained-expiry')
        raw=run(['gh','api',prefix+'/zip'])
        with zipfile.ZipFile(io.BytesIO(raw)) as package:
            name='posttran-phase2-plan-2026-10-16.json'
            if package.namelist().count(name)!=1 or package.read(name)!=(root/amendment['original_path']).read_bytes():
                raise ValueError('handoff-original-ci-plan-bytes')
    result=dict(verification_path=path,evaluated_at=now.isoformat(),original_file_sha256=amendment['original_file_sha256'],
                execution_authorized=False)
    print(json.dumps(result))
    return result


if __name__=='__main__':verify(Path.cwd())
