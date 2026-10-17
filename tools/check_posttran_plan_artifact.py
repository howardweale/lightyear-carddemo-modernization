"""Compare the preserved original plan with its CI artifact; no image or execution."""
import io
import json
from pathlib import Path
import subprocess
import zipfile
from tools.check_posttran_handoff import check_amendment


def verify(root):
    root=Path(root)
    amendment=json.loads((root/'docs/factory/posttran-phase2-plan-amendment-2026-10-17.json').read_bytes())
    prefix='repos/howardweale/lightyear-carddemo-modernization/actions'
    metadata=json.loads(subprocess.check_output(['gh','api',prefix+'/artifacts/'+str(amendment['artifact_id'])]))
    if metadata['expired'] or metadata['name']!='posttran-phase2-plan' or metadata['workflow_run']['id']!=amendment['preparation_run'] or metadata['workflow_run']['head_sha']!=amendment['preparation_head']:
        raise ValueError('handoff-original-artifact-provenance')
    raw=subprocess.check_output(['gh','api',prefix+'/artifacts/'+str(amendment['artifact_id'])+'/zip'])
    with zipfile.ZipFile(io.BytesIO(raw)) as package:
        name='posttran-phase2-plan-2026-10-16.json'
        if package.namelist().count(name)!=1 or package.read(name)!=(root/amendment['original_path']).read_bytes():
            raise ValueError('handoff-original-ci-plan-bytes')
    check_amendment(root,amendment)
    print('Original CI artifact bytes and only declared amended fields verified; no execution authorized.')

if __name__=='__main__':verify(Path.cwd())
