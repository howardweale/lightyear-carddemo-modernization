"""Render dated status from committed evidence and freshly generated unsigned requests."""
import argparse
import json
from pathlib import Path
import tempfile
import shutil

from tools.release_status_records import ROOT, inputs, load, render
from tools.build_release_packet import build
from tools.carddemo_idiomatic_status import inputs as idiomatic_inputs
from tools.carddemo_account_status import inputs as account_inputs


def copy_status_inputs(source, root):
    source, root = Path(source), Path(root)
    shutil.copytree(source/'docs', root/'docs')
    # Published group receipts can bind evidence outside the public docs tree.
    # Use their verified input list; do not drop the group or bypass its hashes.
    paths = ('src/lightyear_control_tower/threshold_evidence.py',
             'src/lightyear_factory/threshold3.py', *idiomatic_inputs(source), *account_inputs(source))
    for path in dict.fromkeys(paths):
        relative = Path(path)
        if relative.is_absolute() or '..' in relative.parts:
            raise ValueError('status-input-path')
        target = root/relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source/relative, target)


def main(output):
    output=Path(output)
    # A temporary public-document tree avoids changing the checkout or old status.
    with tempfile.TemporaryDirectory() as folder:
        root=Path(folder)
        copy_status_inputs(ROOT, root)
        for path in output.glob('*-2026-10-17.json'):shutil.copyfile(path,root/'docs/factory'/path.name)
        value,text=render(load(root))
        value['input_sha256']={p:__import__('hashlib').sha256((root/p).read_bytes()).hexdigest() for p in inputs(root)}
        (output/'current-status-2026-10-17-handoff-refresh.json').write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8',newline='\n')
        (output/'current-status-2026-10-17-handoff-refresh.md').write_text(text,encoding='utf-8',newline='\n')
        build(root=root)
        shutil.copyfile(root/'docs/factory/howard-decision-packet-2026-10-17-handoff-refresh.md',output/'howard-decision-packet-2026-10-17-handoff-refresh.md')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('output');main(p.parse_args().output)
