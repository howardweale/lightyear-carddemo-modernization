"""One verified input model for public status and operator packets."""
from hashlib import sha256
import json
from pathlib import Path
import re
from datetime import datetime, timezone, timedelta

from tools import carddemo_status_record, appl_contract_selection
from lightyear_control_tower.decisions import digest
from lightyear_control_tower.factory_evidence import FactoryEvidence
from lightyear_control_tower.factory_status import status

ROOT = Path(__file__).resolve().parents[1]
HISTORY = "docs/factory/howard-decisions-2026-10-11b.json"
INDEX = "docs/factory/tower-status-input-index.json"
PUBLIC = "docs/factory/factory-status-public-inputs.json"
PHASE2_PUBLIC_ROOT = ""
DELIVERY = "docs/factory/delivery-snapshot-2026-10-17.json"


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
        ('*-review-verdict-*.json', 'posttran-phase2-readiness-2026-10-16.json',
         'b06-part6-reverification-2026-10-16.json', 'intcalc-signing-order-*.json')
        for p in (root/'docs/factory').glob(pattern)]
    additional += [p.relative_to(root).as_posix() for p in sorted((root/'docs/factory').glob('evidence-retention-*.json'))]
    additional += [p for p in ('docs/factory/posttran-phase2-authorization-request-2026-10-16.json', 'docs/factory/posttran-phase2-plan-2026-10-16.json', 'docs/factory/posttran-phase2-artifact-metadata-2026-10-16.json', 'docs/factory/status-snapshot-clock.json') if (root/p).is_file()]
    carddemo_path=carddemo_status_record.latest(root)
    if carddemo_path:additional.append(carddemo_path.relative_to(root).as_posix())
    web_path=carddemo_status_record.latest(root,'carddemo-slice-receipt/1')
    if web_path:additional.extend([web_path.relative_to(root).as_posix(),carddemo_status_record.web_packet_path(web_path)])
    carddemo = 'docs/factory/carddemo-data-review-evidence-2026-10-15.json'
    if (root/carddemo).is_file():
        additional += [carddemo, json.loads((root/carddemo).read_bytes())['summary']['path']]
    additional += [p for p in ('docs/factory/posttran-phase2-readiness-2026-10-17.json', 'docs/factory/posttran-phase2-plan-amendment-2026-10-17.json', 'docs/factory/posttran-phase2-original-ci-plan-2026-10-17.json', 'docs/factory/factory-authority.public.pem') if (root/p).is_file()]
    if (root/appl_contract_selection.PATH).is_file():
        selection=appl_contract_selection.load(root)
        additional += [appl_contract_selection.PATH,*[row['path'] for row in selection['records']]]
    additional += [DELIVERY] if (root/DELIVERY).is_file() else []
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
    projection_paths={}
    for program in ('INTCALC','POSTTRAN'):
        candidates=sorted((root/'docs/factory').glob(program.lower()+'-review-verdict-*.json'))
        if candidates:
            record=json.loads(candidates[-1].read_bytes())
            if digest({k:v for k,v in record.items() if k!='content_sha256'})!=record['content_sha256']:
                raise ValueError('review-projection-seal')
            if record['measurement_head']!=index['head']:raise ValueError('review-projection-evidence-head')
            if program != 'INTCALC' or record['prepared_on'] >= release['prepared_on']:
                projections[program]=record
                projection_paths[program]=candidates[-1].relative_to(root).as_posix()
    readiness_path=root/'docs/factory/posttran-phase2-readiness-2026-10-16.json'
    from tools.check_posttran_handoff import check
    phase2=check(root) if readiness_path.exists() else None
    clock_path=root/'docs/factory/status-snapshot-clock.json'
    clock=json.loads(clock_path.read_bytes())['evaluated_at'] if clock_path.exists() else datetime.now(timezone.utc).isoformat()
    retention=[p.relative_to(root).as_posix() for p in sorted((root/'docs/factory').glob('evidence-retention-*.json'))]
    carddemo_path = root/'docs/factory/carddemo-data-review-evidence-2026-10-15.json'
    carddemo = None
    if carddemo_path.is_file():
        source = json.loads(carddemo_path.read_bytes())['summary']
        raw = (root/source['path']).read_bytes()
        if sha256(raw).hexdigest() != source['sha256']:
            raise ValueError('status-carddemo-evidence-hash')
        carddemo = json.loads(raw)
    b06_path=root/'docs/factory/b06-part6-reverification-2026-10-16.json'
    return dict(appl_contract_selection=appl_contract_selection.load(root), release=release, release_path=path.relative_to(root).as_posix(), activation=activation,
                historical_view=historical_view,projections=projections,projection_paths=projection_paths,carddemo_historical=carddemo,
                phase2=phase2, evaluated_at=clock, retention=retention,
                carddemo=carddemo_status_record.load(root) or carddemo,
                carddemo_web=carddemo_status_record.load_web(root),
                delivery=read(DELIVERY) if (root/DELIVERY).is_file() else None,
                b06=json.loads(b06_path.read_bytes()) if b06_path.exists() else None,
                typed_conditions_implemented=(root/'src/lightyear_control_tower/threshold_evidence.py').is_file(),
                threshold3_implemented=(root/'src/lightyear_factory/threshold3.py').is_file())


def carddemo_text(record):
    if record and record.get('schema') == 'carddemo-slice-evidence/2':
        return carddemo_status_record.paragraph(record)
    if not record:
        return 'Current CardDemo measurements are not recorded.'
    measured=record['measured']; rows=measured['vsam']
    fraction=lambda key: f"{sum(r[key]['matched'] for r in rows)}/{sum(r[key]['compared'] for r in rows)}"
    reasons=[r['reason'] for r in measured.get('blockers', [])]
    screens=measured['screen_gates']
    return (fraction('round_trip')+' original records reconstructed; '+fraction('browse_order')+
            ' browse comparisons. Overall '+measured['verdict']+'. '+
            '; '.join(reasons)+'. Screen sessions compared: '+str(screens['sessions_compared'])+
            '; '+screens['verdict']+': '+screens['reason']+'.')


def b06_text(record):
    if not record:
        return 'Current Windows metadata verification is not available in this snapshot.'
    attempts=record['attempts']
    verified=sum(r['signed_cleanup_verified'] is True for r in attempts)
    supported=[name for name in ('criterion_a','criterion_b') if record[name]['supported']]
    return ('Windows metadata accessible: '+str(record['root_accessible'])+'. Cleanup records verified: '+
            str(verified)+'/'+str(len(attempts))+'. Supported preregistered criteria: '+
            (', '.join(supported) if supported else 'none')+'. '+record['limitation'])


def implementation_text(delivery):
    records={r['number']: r for r in (delivery or {}).get('merges', [])}
    states=[]
    for number in (341,357,358):
        row=records.get(number, {})
        state=row.get('state') or ('merged' if row.get('merge') and row.get('merged_at') else 'not recorded')
        states.append(f'#{number}: {state.lower()}')
    return '; '.join(states)+'. Implementation delivery does not import acceptances or complete evidence gates.'


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
    verdict_path=model['release_path']
    projections=model.get('projections',{})
    if 'INTCALC' in projections:
        review=projections['INTCALC']
        verdict_path=model['projection_paths']['INTCALC']
        current.update(as_of=review['prepared_on'],intcalc=review['verdict'],
            rates={scope:dict(raw=review['raw_thresholds'][scope]['kill_rate'],projected=row['kill_rate']) for scope,row in review['projected_thresholds'].items()})
    delivery = model.get("delivery")
    if delivery and (
        not delivery['push_workflows']
        or any(row['head_sha'] != delivery['main_sha'] or row['status'] != 'completed'
               or row['conclusion'] != 'success' for row in delivery['push_workflows'] + delivery['protected_checks'])
        or delivery['successful_check_run_count'] != delivery['check_run_count']
        or {(row['name'], row['app_id']) for row in delivery['protected_checks']}
            != {('required-ci', 15368), ('documentation-and-lint', 15368)}
    ):
        raise ValueError('delivery-snapshot-not-green')
    current["appl_contract_selection"] = model.get("appl_contract_selection")
    current["carddemo"] = model.get("carddemo")
    current["carddemo_web"] = model.get("carddemo_web")
    current["verdict_path"] = verdict_path
    current["delivery"] = delivery
    snapshot_date = delivery["checked_at"][:10] if delivery else current["as_of"]
    factory = "activated locally (signed-only)" if current["factory_activated"] else "local signed-only activation not recorded"
    policy = "effective" if current["effective_policy"] else "not effective"
    text = ["# Factory current status — " + snapshot_date, "",
            f"Factory: {factory}; threshold policy {policy}.", "",
            f"INTCALC business outcomes {current['business']}; I/O {current['io']}; raw mutation kills {current['raw_mutation']}.", "",
            "| Scope | Raw | Projected, pending decisions |", "| --- | --- | --- |"]
    if delivery:
        summary = ["## Completed merges and main CI", "",
            "CI snapshot checked at " + delivery["checked_at"] + ". Evidence measurements below retain their dated scope (" + current["as_of"] + ").", "",
            "| PR | Merge commit | Merged at (UTC) |", "| --- | --- | --- |"]
        for row in delivery["merges"]:
            summary.append(f"| [#{row['number']}]({row['url']}) | `{row['merge']}` | {row['merged_at']} |")
        summary += ["", f"Main `{delivery['main_sha']}`: all {len(delivery['push_workflows'])} observed push workflows and {delivery['successful_check_run_count']}/{delivery['check_run_count']} check runs completed successfully, including `required-ci` and `documentation-and-lint`.",
            "[Snapshot and full workflow links](" + Path(DELIVERY).name + ").",
            delivery["scope"], "", "## INTCALC evidence", ""]
        text[2:2] = summary
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
        from tools.check_posttran_handoff import timing
        current['phase2']={**phase2,**timing(phase2,datetime.fromisoformat(delivery["checked_at"] if delivery else model['evaluated_at']))}
        text+=['','| Phase 2 | Plan seal | Executable commit | Sign and launch by (UTC) | Days remaining |',
               '|---|---|---|---|---:|',
               f"| POSTTRAN | `{phase2['plan_sha256']}` | `{phase2['executable_commit']}` | {phase2.get('sign_and_launch_by', phase2.get('signing_deadline'))} | {current['phase2']['days_remaining']} |",
               '', 'Evaluated at '+current['phase2']['evaluated_at']+'. Request: ['+Path(phase2['request_path']).name+']('+Path(phase2['request_path']).name+').',
               'Warning: five days or fewer remain before sign-and-launch deadline.' if current['phase2']['warning'] else 'More than five days remain before sign-and-launch deadline at snapshot time.',
               '[Operator runbook](posttran-phase2-runbook.md). The window end applies to the reserve launch check as well as signing. The daily deadline workflow uses the real UTC clock; this page is a dated snapshot. Preparation and rehearsal do not authorize execution.']
    current['retention_manifests']=model.get('retention',[])
    text+=['','## Durable public evidence','',
           *['Current retention manifest: ['+Path(p).name+']('+Path(p).name+'); scheduled download/hash verification applies. Local deletion remains unauthorized.' for p in model.get('retention',[])],
           'Dated October 14/15 retention statements remain historical; use these manifests for current storage status. [October 17 verification and deletion addendum](retention-inventory-2026-10-17.json); local deletion remains unauthorized.']
    text+=['','## CardDemo data slice','',carddemo_text(model.get('carddemo')),
           '','## CardDemo six-screen proof','',carddemo_status_record.web_paragraph(model.get('carddemo_web')),
           '','## B06 access','',
           b06_text(model.get('b06')),
           '','## Equivalence evidence still outstanding','',
           implementation_text(delivery),
           '', 'Resolved now: **8/227**. **185/227 (81.5%)** is conditional on the two pending class signatures, below the 95% target. Fresh E1 repeats reproduce the preserved totals; they do not add resolutions. [E1 evidence and remaining gates](equivalence-scale-2026-10-16/README.md).',
           '', 'TRANREPT has two compiler identities in 413 sites and zero class matches; generality and reviewer person-minutes remain unmeasured.',
           '', 'Byte storage support is implemented, but whole-program acceptance remains incomplete: zero unsupported constructs, whole-program control/effects, and 1,000 byte-exact differential inputs per program are still required. Storage inspection alone earns no differential credit.',
           '', 'E3 equivalence and all-killed-mutant rejection checks, E4 build comparisons and measured speedup, E5 held-out campaigns, and E6 policy approval remain separate gates. E7 residual grouping does not resolve evidence.',
           '','## Other unfinished work','',
           'CMS [PR #360](https://github.com/howardweale/lightyear-carddemo-modernization/pull/360) remains a draft F0 feasibility investigation. Same-revision equivalence is not established; publication/merge and F1–F4 need separate authorization.',
           '', 'The Phase 2 request remains unsigned and unexecuted. Final reviewed-checkout readiness verification is still required before any future signing. Public retention verification does not authorize local evidence deletion.',
           '', 'Typed condition support: '+str(model.get('typed_conditions_implemented',False))+'. Threshold/3 support: '+str(model.get('threshold3_implemented',False))+'. Presence of code is not effective policy approval.']
    if model.get("appl_contract_selection"):
        text += ["", "## Selected APPL-RESULT contracts", "", appl_contract_selection.markdown(model["appl_contract_selection"]), "", "[Current signing guide](appl-result-signing-2026-10-18.md) · [Contract decision addendum](howard-decision-packet-2026-10-18-appl-selection.md)"]
    text += ["", current["intcalc"], "",
             "This is recorded local activation and twin-scoped evidence; it grants no execution, release, or z/OS authority.", "",
             f"[Measured verdict]({Path(verdict_path).with_suffix('.md').name}) · [Decision packet](howard-decision-packet-{current['as_of']}-handoff-refresh.md)", ""]
    return current, "\n".join(text)
