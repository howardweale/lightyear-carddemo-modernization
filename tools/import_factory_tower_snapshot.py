"""Import a complete pinned public Factory snapshot; never provision authority."""
import argparse
import json
import subprocess
from pathlib import Path
from hashlib import sha256
from lightyear_control_tower.factory_import import committed
from lightyear_control_tower.factory_policy import require
from lightyear_control_tower.decisions import canonical
from lightyear_control_tower.presentation import FACTORY_FILES
from lightyear_control_tower.factory_evidence import INDEX, FactoryEvidence


def snapshot(repository, commit, root):
    root=Path(root)
    require(not root.exists(), "fresh-snapshot-directory-required")
    payload={"docs/factory/"+name:committed(repository,commit,"docs/factory/"+name) for name in FACTORY_FILES}
    created=subprocess.check_output(["git","show","-s","--format=%cI",commit],cwd=repository,text=True).strip()
    index=dict(schema="factory-evidence-index/1",commit=commit,created_at=created,
        sources=[dict(path=p,sha256=sha256(raw).hexdigest()) for p,raw in sorted(payload.items())])
    for path,raw in payload.items():
        destination=root/path;destination.parent.mkdir(parents=True,exist_ok=True);destination.write_bytes(raw)
    target=root/INDEX;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(canonical(index))
    pin=sha256(canonical(index)).hexdigest()
    evidence=FactoryEvidence(root,pin)
    for name in FACTORY_FILES:evidence.read(name)
    return dict(schema="factory-evidence-trust/1",index_sha256=pin)


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repository",type=Path,required=True);p.add_argument("--commit",required=True);p.add_argument("--root",type=Path,required=True)
    a=p.parse_args();print(json.dumps(snapshot(a.repository,a.commit,a.root),indent=2))
