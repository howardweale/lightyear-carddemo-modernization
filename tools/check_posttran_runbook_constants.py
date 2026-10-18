"""Check documented PowerShell constants against committed public evidence."""
from hashlib import sha256
import json
import re
from pathlib import Path
from lightyear_control_tower.decisions import canonical
from tools.check_posttran_handoff import check


def verify(root, text=None):
    root=Path(root); ready=check(root)
    request=json.loads((root/ready['request_path']).read_bytes())
    amendment=json.loads((root/ready['plan_amendment']).read_bytes())
    expected={'RequestRef':ready['request_publication_commit'],'ExecutableCommit':ready['executable_commit'],
        'ExpectedRequestFileHash':ready['request_file_sha256'],'ExpectedPublicKeyHash':ready['public_key_sha256'],
        'ExpectedPlanFileHash':amendment['amended_file_sha256'],'ExpectedQueueHash':sha256(canonical(request)).hexdigest()}
    text=text if text is not None else (root/'docs/factory/posttran-phase2-runbook.md').read_text(encoding='utf-8')
    blocks=re.findall(r'```powershell\s*\n(.*?)```',text,re.S|re.I)
    for name,value in expected.items():
        assignments=re.findall(r'\$'+name+r"\s*=\s*['\"]([^'\"]+)['\"]",'\n'.join(blocks))
        if not assignments or any(x!=value for x in assignments):
            raise ValueError('posttran-runbook-constant:'+name)
    return expected


if __name__=='__main__':
    print(json.dumps(verify(Path.cwd()),sort_keys=True))
