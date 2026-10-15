"""One verified input model for public status and operator packets."""
from hashlib import sha256
import json
from pathlib import Path
import re

from lightyear_control_tower.decisions import digest
from lightyear_control_tower.factory_evidence import FactoryEvidence
from lightyear_control_tower.factory_status import status

ROOT = Path(__file__).resolve().parents[1]
HISTORY = "docs/factory/howard-decisions-2026-10-11b.json"
INDEX = "docs/factory/tower-status-input-index.json"
PUBLIC = "docs/factory/factory-status-public-inputs.json"


def latest(root):
    candidates = sorted(p for p in (root / "docs/factory").glob("intcalc-releasability-*.json")
                        if re.fullmatch(r"intcalc-releasability-\d{4}-\d{2}-\d{2}\.json", p.name))
    if not candidates:
        raise ValueError("release-status-missing")
    return candidates[-1]


def inputs(root=ROOT):
    root = Path(root)
    release_path = latest(root)
    release = json.loads(release_path.read_bytes())
    index_path = release["evidence_index"]["path"]
    index = json.loads((root/index_path).read_bytes())
    historical = json.loads((root/INDEX).read_bytes())
    public = json.loads((root/PUBLIC).read_bytes())
    return tuple(dict.fromkeys([HISTORY, INDEX, PUBLIC, public["activation"]["path"],
        str(release_path.relative_to(root)), index_path,
        *[path for archive in index["sources"] for path in archive["files"]],
        *[row["path"] for row in historical["sources"]]]))


def load(root=ROOT):
    root = Path(root)
    read = lambda path: json.loads((root/path).read_bytes())
    history = read(HISTORY)
    if digest({k:v for k,v in history.items() if k != "content_sha256"}) != history["content_sha256"]:
        raise ValueError("status-input-seal")
    historical_index = read(INDEX)
    historical_view = status(FactoryEvidence(root, digest(historical_index), index=historical_index))
    path = latest(root)
    release = json.loads(path.read_bytes())
    if digest({k:v for k,v in release.items() if k != "content_sha256"}) != release["content_sha256"]:
        raise ValueError("release-status-seal")
    index_path = release["evidence_index"]["path"]
    if sha256((root/index_path).read_bytes()).hexdigest() != release["evidence_index"]["sha256"]:
        raise ValueError("release-status-index-hash")
    index = read(index_path)
    for archive in index["sources"]:
        for filename, expected in archive["files"].items():
            if sha256((root/filename).read_bytes()).hexdigest() != expected:
                raise ValueError("release-status-evidence-hash")
    public = read(PUBLIC)
    source = public["activation"]
    if sha256((root/source["path"]).read_bytes()).hexdigest() != source["sha256"]:
        raise ValueError("status-activation-evidence-hash")
    activation = read(source["path"])
    if activation["schema"] != "factory-local-activation/1" or activation["scope"] != "factory":
        raise ValueError("status-activation-shape")
    return dict(release=release, release_path=str(path.relative_to(root)), activation=activation,
                historical_view=historical_view)


def render(model):
    release, activation = model["release"], model["activation"]
    program = release["programs"]["INTCALC"]
    scopes = release["scopes"]
    current = dict(schema="factory-current-review-status/2", as_of=release["prepared_on"],
        release_evidence_sha256=release["content_sha256"], intcalc=release["verdict"],
        business=program["business"]["fraction"], io=program["io"]["fraction"],
        raw_mutation=release["raw_kill_rate"], rates={k:dict(raw=v["raw"]["kill_rate"], projected=v["projected"]["kill_rate"]) for k,v in scopes.items()},
        diversity=program["diversity"], remaining_gaps=len(release["remaining_evidence_gaps"]), loader_domain=release["loader_domain"],
        effective_policy=release["effective"], factory_activated=activation["signed_only"],
        activation_receipt=activation, release_authorized=release["release_authorized"],
        historical_view=model["historical_view"])
    factory = "activated locally (signed-only)" if current["factory_activated"] else "local signed-only activation not recorded"
    policy = "effective" if current["effective_policy"] else "not effective"
    text = ["# Factory current status — " + current["as_of"], "",
            f"Factory: {factory}; threshold policy {policy}.", "",
            f"INTCALC business outcomes {current['business']}; I/O {current['io']}; raw mutation kills {current['raw_mutation']}.", "",
            "| Scope | Raw | Projected, pending decisions |", "| --- | --- | --- |"]
    for scope, row in current["rates"].items():
        text.append(f"| {scope} | {row['raw']} | {row['projected']} |")
    text += ["", "Loader assessments: " + str(current["loader_domain"]["assessment_counts"]) + ".", "",
             "| Compared field | Distinct values |", "| --- | --- |"]
    for field, count in current["diversity"].items():
        text.append(f"| {field} | {count} |")
    text += ["", current["intcalc"], "",
             "This is recorded local activation and twin-scoped evidence; it grants no execution, release, or z/OS authority.", "",
             f"[Measured verdict]({Path(model['release_path']).with_suffix('.md').name}) · [Decision packet](howard-decision-packet-{current['as_of']}.md)", ""]
    return current, "\n".join(text)
