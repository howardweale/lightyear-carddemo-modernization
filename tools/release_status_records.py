"""One verified input model for public status and operator packets."""
from hashlib import sha256
import json
from pathlib import Path
import re
from datetime import datetime, timezone, timedelta

from lightyear_control_tower.decisions import digest
from lightyear_control_tower.factory_evidence import FactoryEvidence
from lightyear_control_tower.factory_status import status

ROOT = Path(__file__).resolve().parents[1]
HISTORY = "docs/factory/howard-decisions-2026-10-11b.json"
INDEX = "docs/factory/tower-status-input-index.json"
PUBLIC = "docs/factory/factory-status-public-inputs.json"
PHASE2_PUBLIC_ROOT = "https://github.com/howardweale/lightyear-carddemo-modernization/blob/f7a137ae5635bed903600afff816d1393c9e420e/docs/factory/"


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
    additional = [p.relative_to(root).as_posix() for pattern in
        ('*-review-verdict-2026-10-16.json', 'posttran-phase2-readiness-2026-10-16.json',
         'b06-part6-reverification-2026-10-16.json', 'intcalc-signing-order-2026-10-16.json')
        for p in (root/'docs/factory').glob(pattern)]
    additional += [p for p in ('src/lightyear_control_tower/threshold_evidence.py',
                              'src/lightyear_factory/threshold3.py') if (root/p).is_file()]
    return tuple(dict.fromkeys([HISTORY, INDEX, PUBLIC, public["activation"]["path"],
        *additional,
        release_path.relative_to(root).as_posix(), index_path,
        *[path for archive in index["sources"] + index.get("crosscheck_sources", []) for path in archive["files"]],
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
    for archive in index["sources"] + index.get("crosscheck_sources", []):
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
    projections={}
    for program in ('INTCALC','POSTTRAN'):
        candidates=sorted((root/'docs/factory').glob(program.lower()+'-review-verdict-*.json'))
        if candidates:
            record=json.loads(candidates[-1].read_bytes())
            if digest({k:v for k,v in record.items() if k!='content_sha256'})!=record['content_sha256']:
                raise ValueError('review-projection-seal')
            if record['measurement_head']!=index['head']:raise ValueError('review-projection-evidence-head')
            projections[program]=record
    readiness_path=root/'docs/factory/posttran-phase2-readiness-2026-10-16.json'
    b06_path=root/'docs/factory/b06-part6-reverification-2026-10-16.json'
    return dict(release=release, release_path=path.relative_to(root).as_posix(), activation=activation,
                historical_view=historical_view,projections=projections,
                phase2=json.loads(readiness_path.read_bytes()) if readiness_path.exists() else None,
                b06=json.loads(b06_path.read_bytes()) if b06_path.exists() else None,
                typed_conditions_implemented=(root/'src/lightyear_control_tower/threshold_evidence.py').is_file(),
                threshold3_implemented=(root/'src/lightyear_factory/threshold3.py').is_file())


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
    projections=model.get('projections',{})
    if 'INTCALC' in projections:
        review=projections['INTCALC']
        current.update(as_of=review['prepared_on'],intcalc=review['verdict'],
            rates={scope:dict(raw=review['raw_thresholds'][scope]['kill_rate'],projected=row['kill_rate']) for scope,row in review['projected_thresholds'].items()})
    factory = "activated locally (signed-only)" if current["factory_activated"] else "local signed-only activation not recorded"
    policy = "effective" if current["effective_policy"] else "not effective"
    text = ["# Factory current status — " + current["as_of"], "",
            f"Factory: {factory}; threshold policy {policy}.", "",
            f"INTCALC business outcomes {current['business']}; I/O {current['io']}; raw mutation kills {current['raw_mutation']}.", "",
            "| Scope | Raw | Projected, pending decisions |", "| --- | --- | --- |"]
    for scope, row in current["rates"].items():
        text.append(f"| {scope} | {row['raw']} | {row['projected']} |")
    text += ["", "Loader assessments: " + "; ".join(f"{name}: {count}" for name, count in current["loader_domain"]["assessment_counts"].items()) + ".", "",
             "| Compared field | Distinct values |", "| --- | --- |"]
    for field, count in current["diversity"].items():
        text.append(f"| {field} | {count} |")
    deficits=program['below_two_values']
    text += ['',f'Diversity deficit: {len(deficits)} fields.',*['- '+field for field in deficits]]
    if 'INTCALC' in projections:
        review=projections['INTCALC']
        text+=['',review['scope_explanation'],f"Hypothetical z/OS rate after confirmation: {review['hypothetical_zos_after_confirmation']['kill_rate']}; not applied."]
    if 'POSTTRAN' in projections:
        review=projections['POSTTRAN'];current['posttran']=review
        text+=['','## POSTTRAN','',review['verdict'],
            f"Business {review['business']['fraction']}; I/O {review['io']['fraction']}; diversity deficit {len(review['below_two_values'])} fields.",
            *[scope+': '+row['kill_rate']+' projected; '+str(len(row['unresolved_survivors']))+' unresolved.' for scope,row in review['projected_thresholds'].items()]]
    phase2=model.get('phase2')
    if phase2:
        expiry=datetime.fromisoformat(phase2['artifact_expires_at'])
        current['phase2']={**phase2,'warning':expiry-datetime.now(timezone.utc)<timedelta(days=5)}
        text+=['',f"POSTTRAN compiler expiry: {phase2['artifact_expires_at']}. Signing deadline: {phase2['signing_deadline']}.",
               'Warning: fewer than five days remain.' if current['phase2']['warning'] else 'At least five days remain at rendering time.',
               '[Operator runbook]('+PHASE2_PUBLIC_ROOT+'posttran-phase2-runbook.md). Preparation and rehearsal do not authorize execution.']
    text+=['','## CardDemo data slice','','210/210 original records reconstructed; 1,560/1,560 browse comparisons. Overall indeterminate: public IMS framing, DL/I integration and screen/session evidence remain separate gates.',
           '','## B06 access','',
           'Windows metadata is accessible. Both signed terminal/cleanup records and signed inventory metadata reverified; cause remains unidentified under both preregistered criteria. Raw captures were not reread.' if model.get('b06',{} ) else 'Current Windows metadata verification is not available in this snapshot.',
           '','## Draft #341','','The targeted equivalence draft remains separate and unsigned; no new acceptances are imported from it. [Review PR #341](https://github.com/howardweale/lightyear-carddemo-modernization/pull/341).',
           '', 'Typed condition support: '+str(model.get('typed_conditions_implemented',False))+'. Threshold/3 support: '+str(model.get('threshold3_implemented',False))+'. Presence of code is not effective policy approval.']
    text += ["", current["intcalc"], "",
             "This is recorded local activation and twin-scoped evidence; it grants no execution, release, or z/OS authority.", "",
             f"[Measured verdict]({Path(model['release_path']).with_suffix('.md').name}) · [Decision packet](howard-decision-packet-{current['as_of']}.md)", ""]
    return current, "\n".join(text)
