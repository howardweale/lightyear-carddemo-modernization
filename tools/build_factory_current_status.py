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
RELEASE="docs/factory/intcalc-releasability-2026-10-14.json"
RELEASE_INDEX="docs/factory/release-evidence-2026-10-14/index.json"
RELEASE_INPUTS=(RELEASE,RELEASE_INDEX,"docs/factory/merge-hold-lift-2026-10-14.json",
    *[path for archive in json.loads((ROOT/RELEASE_INDEX).read_bytes())["sources"] for path in archive["files"]])
INPUTS=("docs/factory/howard-decisions-2026-10-11b.json",INDEX,*RELEASE_INPUTS,*["docs/factory/"+name for name in FACTORY_FILES])


def generate(root=ROOT):
    root=Path(root)
    historical=read_json(root/INPUTS[0])
    if digest({k:v for k,v in historical.items() if k!="content_sha256"})!=historical["content_sha256"]:
        raise ValueError("status-input-seal")
    index=read_json(root/INDEX)
    evidence=FactoryEvidence(root,digest(index),index=index)
    view=status(evidence)
    from hashlib import sha256
    release=read_json(root/RELEASE)
    if digest({k:v for k,v in release.items() if k!="content_sha256"})!=release["content_sha256"]:
        raise ValueError("release-status-seal")
    index=read_json(root/RELEASE_INDEX)
    if sha256((root/RELEASE_INDEX).read_bytes()).hexdigest()!=release["evidence_index"]["sha256"]:
        raise ValueError("release-status-index-hash")
    for archive in index["sources"]:
        for path,expected in archive["files"].items():
            if sha256((root/path).read_bytes()).hexdigest()!=expected:raise ValueError("release-status-evidence-hash")
    lift=read_json(root/"docs/factory/merge-hold-lift-2026-10-14.json")
    if sha256(lift["wording"].encode()).hexdigest()!=lift["wording_sha256"] or lift["merge_hold"] is not False:
        raise ValueError("release-status-merge-decision")
    current=dict(schema="factory-current-review-status/1",as_of=release["prepared_on"],
        release_evidence_sha256=release["content_sha256"],intcalc=release["verdict"],
        business="8/8",io="85/86",raw_mutation=release["raw_kill_rate"],
        remaining_gaps=len(release["remaining_evidence_gaps"]),loader_domain=release["loader_domain"],
        posttran_phase2="not run; explicit plan/head approval required",merge_hold=False,
        new_pr_merge_approval_required=True,b06_part6="signed attempt evidence missing",
        effective_policy=False,factory_activated=False,release_authorized=False)
    text="\n".join(["# Factory current status — "+current["as_of"],"",
        "**INTCALC: "+current["intcalc"]+".** Business outcomes 8/8; I/O 85/86; raw mutation kills 308/421. Fresh loader-domain overlays and effective signatures remain pending.","",
        "All three targeted items have 200/200 valid comparisons in the retained main run and PR328. INTCALC's three varying fields now have 2, 3, 3 values; POSTTRAN's nine varying fields also meet the two-value minimum. Seven INTCALC constants remain source-bound review items.","",
        "**POSTTRAN Phase 2: not run.** Candidate unchanged. CI prepares the exact compiler-image/input plan; explicit plan and execution-head approval is required before a single comparison run.","",
        "**B06 merge hold: lifted by Howard on October 14.** New PRs still need exact-head approval after green checks. Part 6 cannot be completed until the signed attempt and cleanup evidence is available. No observer repair or new native run is planned.","",
        "Factory activation and effective threshold policy remain pending. This page confers no authority.","",
        "[Decision packet](howard-decision-packet-2026-10-14.md) · [Measured INTCALC verdict](intcalc-releasability-2026-10-14.md) · [Evidence index](release-evidence-2026-10-14/index.json)",""])
    return current,text


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--check",action="store_true");a=p.parse_args()
    view,text=generate()
    outputs={ROOT/"docs/factory/current-status.md":text,ROOT/"docs/factory/current-status.json":json.dumps(view,indent=2)+"\n"}
    for path,content in outputs.items():
        if a.check:
            if path.read_text(encoding="utf-8")!=content:raise SystemExit("stale current status: "+str(path))
        else:path.write_text(content,encoding="utf-8",newline="\n")
