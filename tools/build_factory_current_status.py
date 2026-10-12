"""Generate the Factory Status documentation from its pinned public input index."""
import argparse
import json
from pathlib import Path
from lightyear_control_tower.decisions import digest
from lightyear_control_tower.requests import read_json
from lightyear_control_tower.factory_evidence import FactoryEvidence
from lightyear_control_tower.factory_status import status,markdown
from lightyear_control_tower.presentation import FACTORY_FILES
from lightyear_mainframe.zos_bindings import ROOT

INDEX="docs/factory/tower-status-input-index.json"
INPUTS=("docs/factory/howard-decisions-2026-10-11b.json",INDEX,*["docs/factory/"+name for name in FACTORY_FILES])


def generate(root=ROOT):
    root=Path(root)
    historical=read_json(root/INPUTS[0])
    if digest({k:v for k,v in historical.items() if k!="content_sha256"})!=historical["content_sha256"]:
        raise ValueError("status-input-seal")
    index=read_json(root/INDEX)
    evidence=FactoryEvidence(root,digest(index),index=index)
    view=status(evidence)
    return view,markdown(view)


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--check",action="store_true");a=p.parse_args()
    view,text=generate()
    outputs={ROOT/"docs/factory/current-status.md":text,ROOT/"docs/factory/current-status.json":json.dumps(view,indent=2)+"\n"}
    for path,content in outputs.items():
        if a.check:
            if path.read_text(encoding="utf-8")!=content:raise SystemExit("stale current status: "+str(path))
        else:path.write_text(content,encoding="utf-8",newline="\n")
