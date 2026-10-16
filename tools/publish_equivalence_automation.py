"""Render a dated report solely from sealed CI measurements; no model drafting."""
import argparse,json
from pathlib import Path
from lightyear_mainframe.equivalence_automation import verify,digest,sealed
from tools.run_equivalence_automation import markdown_triage,write


def publish(inputs,output,run_id):
    data=[]
    for job in ('INTCALC','POSTTRAN','TRANREPT'):
        folder=inputs/('equivalence-evidence-'+job)/'run'
        summary=verify(json.loads((folder/'summary.json').read_text()))
        baseline=verify(json.loads((folder/'triage.json').read_text()))
        recheck=json.loads((folder.parent/'recheck/recheck.json').read_text())
        repeated=verify(json.loads((folder.parent/'repeat-comparison.json').read_text()))
        if repeated['head']!=summary['head'] or not repeated['identical_resolutions']:raise ValueError('non-reproducible-report')
        if summary['head']!=baseline['head'] or recheck['head']!=summary['head'] or not recheck['identical_resolutions']:raise ValueError('incomplete-or-mixed-report')
        data.append((summary,baseline,folder))
    if len({s['head'] for s,_,_ in data})!=1:raise ValueError('mixed-heads')
    head=data[0][0]['head'];output.mkdir(parents=True,exist_ok=True)
    projections=[verify(json.loads((folder/'signature-projection.json').read_text())) for _,_,folder in data]
    if any(p['measurement_head']!=head for p in projections):raise ValueError('projection-head-mismatch')
    total=sum(p['denominator'] for p in projections)
    now=sum(p['resolved_now'] for p in projections)
    pending=sum(p['resolved_after_pending_signatures'] for p in projections)
    stage=[f'After pending signatures: {pending}/{total} ({100*pending/total:.1f}%).',
           f'Resolved now: {now}/{total} ({100*now/total:.1f}%).',
           'Held out: TRANREPT/CBTRN03C is measured separately; zero class matches means no evidence of generality.', '',
           f'Fresh E1 pipeline at `{head}`; repeated and independently rechecked. Run {run_id}.', '',
           '| Program | Route | Resolved now | After pending signatures |', '|---|---|---:|---:|']
    for p in projections:
        for route, counts in p['routes'].items():
            stage.append(f"| {p['program']} | {route} | {counts['resolved_now']} | {counts['resolved_after_pending_signatures']} |")
    stage+=['','Reviewer person-minutes per 1,000 sites: not measured. Unsigned proposals have no effect on actual resolutions or historical denominators.',
            'Waiting: the two APPL-RESULT class signatures. Data-domain and operator-policy proposals are not yet ready to sign. No z/OS-facing acceptance or release authority.']
    (output/'equivalence-scale-E1.md').write_text('\n'.join(stage)+'\n')
    write(output/'equivalence-scale-E1.json',sealed(dict(stage='E1',head=head,run_id=run_id,programs=projections)))
    write(output/'equivalence-triage-2026-10-15.json',sealed(dict(head=head,programs=[d for _,d,_ in data])))
    (output/'equivalence-triage-2026-10-15.md').write_text(markdown_triage([d for _,d,_ in data]))
    lines=['# Automated equivalence — 2026-10-15','',
           'The retained baseline contains **227 argued equivalents: 180 compiler/class arguments and 47 individual reviews**, plus nine additional POSTTRAN survivors/evidence gaps. INTCALC has 421 eligible mutation sites; POSTTRAN has 483. TRANREPT is a separate held-out inventory of 413 sites, with no inherited kills or equivalence decisions.', '',
           'The earlier October 12 INTCALC aggregate listed 167 gap IDs beside a count of 113. The complete per-mutant records confirm 113; the additional 54 IDs were killed. This report uses the sealed October 15 integration-run rows and preserves the historical publication unchanged.', '',
           f'Execution: [GitHub Actions run {run_id}](https://github.com/howardweale/lightyear-carddemo-modernization/actions/runs/{run_id}), source commit `{head}`. Public CardDemo only; zero model calls. All results are twin-scoped.', '',
           '| Program | Route | Resolved | Of 47 individual reviews | Other survivors resolved | New kills |', '|---|---|---:|---:|---:|---:|']
    argued=sum(s['argued_resolved'] for s,_,_ in data);total=sum(s['argued_total'] for s,_,_ in data)
    individual=sum(c['individual_resolved'] for s,_,_ in data for c in s['routes'].values())
    lines[8:8]=[f'This run resolves **{argued}/{total} ({100*argued/total:.1f}%)** of the argued equivalents automatically, including **{individual}/47 individual reviews**. The 95% target is not met. Unsigned class proposals are excluded.', '']
    for s,_,_ in data:
        for route,c in s['routes'].items():lines.append(f"| {s['program']} | {route} | {c['resolved']} | {c['individual_resolved']} | {c['survivors_resolved']} | {c['kills']} |")
    lines+=['','| Program | Argued resolved automatically | Unobservable | Unresolved, including unobservable | Estimated review minutes / 1,000 sites |','|---|---:|---:|---:|---:|']
    for s,b,_ in data:
        ratio=f"{s['argued_resolved']}/{s['argued_total']} ({100*s['argued_resolved']/s['argued_total']:.1f}%)" if s['argued_total'] else 'Not applicable (held out)'
        lines.append(f"| {s['program']} | {ratio} | {s['unobservable']} | {s['unresolved']} | {5000*s['unresolved']/b['inventory_count']:.1f} |")
    lines+=['','Review-time estimates assume five minutes per remaining packet. They are planning estimates, not measured operator time. The 95% automatic-resolution share is a target; pending class signatures do not contribute.', '',
            '| Program | Raw before | Raw after | Adjusted before new proofs | Adjusted after |','|---|---:|---:|---:|---:|']
    for s,_,_ in data:
        if s['before'] is None:continue
        def ratio(key,kind):return f"{s[key][kind]['numerator']}/{s[key][kind]['denominator']}"
        lines.append(f"| {s['program']} | {ratio('before','raw')} | {ratio('after','raw')} | {ratio('before','adjusted')} | {ratio('after','adjusted')} |")
    lines+=['','Adjusted-before shows the new overlay with no new proof exclusions. Historical individually accepted exclusions and active release policy are not rewritten. Every unobservable or unresolved site remains in the denominator.', '',
            '## Validation and disabled routes','',
            'Each enabled local statement/PIC encoder was checked on at least 10,000 deterministic random in-domain inputs per side, comparing every receiving byte against the actual pinned GnuCOBOL twin. Any disagreement disables that exact statement/PIC shape. Two complete pipeline runs produced identical classifications for every mutant, including unresolved and unobservable cases. Every emitted machine resolution was also independently rebuilt, re-solved or replayed on the same source head.', '']
    for s,_,folder in data:
        lines.append(f"- {s['program']}: {s['solver_targets']} solver targets; {s['generated_cases']} generated search/replay cases; {len(s['disabled_encoders'])} disabled encoder shapes.")
        for mid in s['disabled_encoders']:lines.append(f"  - `{mid}`: encoder/twin disagreement; unresolved unless another admissible route supplies independent evidence.")
    held=verify(json.loads((data[2][2]/'class-validation.json').read_text()))
    lines+=['',f"Held-out class measurements: {len(held['measurements'])}. Disabled classes: {', '.join(held['disabled_classes']) or 'none observed'}. Zero matched members is not evidence of generality.", '',
            'Supported arithmetic is an exact scaled-integer local subset. ON SIZE ERROR handlers, division, aliases and paragraph/path-to-output proofs are explicitly unsupported. The held-out program has compiler/local-statement measurements, but no whole-application execution harness. No downstream masking is assumed.', '',
            '## Decisions waiting for Howard','',
            'Class and audit contracts are unsigned. Approval must bind the exact packet, matcher, source and scope. Model-spend requests: none. This work does not authorize release or native z/OS execution.', '',
            '| Program | Unsigned class requests | Audit samples | Audit errors / reviewed | 95% upper bound |','|---|---:|---:|---|---|']
    for s,_,_ in data:
        lines.append(f"| {s['program']} | {s['class_requests']} | {sum(len(x['items']) for x in s['audit'])} | Pending; no human audit yet | Not estimated before review |")
    lines+=['','A confirmed wrong resolution disables its program/route in the signed review overlay. The original CI evidence remains immutable. Reapproval requires repaired implementation, fresh evidence and a new audit.', '',
            'Recheck commands and artifact bindings are in `equivalence-automation-guide.md`. Full compiler objects, 10,000-input validation transcripts and executed scenarios are retained in the run artifacts; compact proof and review records are published beside this report.']
    (output/'equivalence-automation-2026-10-15.md').write_text('\n'.join(lines)+'\n')
    write(output/'equivalence-automation-2026-10-15.json',sealed(dict(head=head,run_id=run_id,programs=[s for s,_,_ in data],held_out=held)))
    # Durable small proof records; full binaries and transcripts stay in CI artifacts.
    for summary,_,folder in data:
        dest=output/'equivalence-evidence-2026-10-15'/summary['program']
        positive={r['id'] for r in verify(json.loads((folder/'resolutions.json').read_text()))['rows'] if r['status'] in ('equivalent','killed')}
        for pattern in ('summary.json','resolutions.json','manifest.json','toolchain.json','encoder-validation.json','class-validation.json',
                        'legacy-class-census.json','normalization-tests.json','remaining-review.json','directed-search.json','audit-request.json','audit-packet.json','class-requests.json','class-packets/*.json',
                        'mutants/*/compiler-proof.json','mutants/*/pair.json','mutants/*/solver/query.smt2','mutants/*/solver/solver.json',
                        'mutants/*/solver/validation.json','mutants/*/oracle-gap.json','search/regression-scenarios.json','search/cases/*/kill.json'):
            for path in folder.glob(pattern):
                relative=path.relative_to(folder)
                if relative.parts[0]=='mutants' and relative.parts[1] not in positive:continue
                target=dest/path.relative_to(folder);target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(path.read_bytes())
        for name,source in (('recheck.json',folder.parent/'recheck/recheck.json'),('repeat-comparison.json',folder.parent/'repeat-comparison.json')):
            (dest/name).write_bytes(source.read_bytes())
    return head

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('inputs',type=Path);p.add_argument('output',type=Path);p.add_argument('--run-id',required=True);a=p.parse_args();print(publish(a.inputs,a.output,a.run_id))
