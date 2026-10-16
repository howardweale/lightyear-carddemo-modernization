"""Render dated status from committed evidence and freshly generated unsigned requests."""
import argparse
import json
from pathlib import Path
import tempfile
import shutil

from tools.release_status_records import ROOT, inputs, load, render
from tools.build_release_packet import build


def main(output):
    output=Path(output)
    # A temporary public-document tree avoids changing the checkout or old status.
    with tempfile.TemporaryDirectory() as folder:
        root=Path(folder)
        shutil.copytree(ROOT/'docs',root/'docs')
        for path in ('src/lightyear_control_tower/threshold_evidence.py','src/lightyear_factory/threshold3.py'):
            target=root/path;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/path,target)
        for path in output.glob('intcalc-*-2026-10-16.json'):shutil.copyfile(path,root/'docs/factory'/path.name)
        value,text=render(load(root))
        value['input_sha256']={p:__import__('hashlib').sha256((root/p).read_bytes()).hexdigest() for p in inputs(root)}
        (output/'current-status-2026-10-16-handoff-refresh.json').write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8',newline='\n')
        (output/'current-status-2026-10-16-handoff-refresh.md').write_text(text,encoding='utf-8',newline='\n')
        build(root=root)
        shutil.copyfile(root/'docs/factory/howard-decision-packet-2026-10-16-handoff-refresh.md',output/'howard-decision-packet-2026-10-16-handoff-refresh.md')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('output');main(p.parse_args().output)
