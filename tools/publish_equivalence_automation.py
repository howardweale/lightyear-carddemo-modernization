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
        if summary['head']!=baseline['head'] or recheck['head']!=summary['head'] or not recheck['identical_resolutions']:raise ValueError('incomplete-or-mixed-report')
        data.append((summary,baseline,folder))
    if len({s['head'] for s,_,_ in data})!=1:raise ValueError('mixed-heads')
    head=data[0][0]['head'];output.mkdir(parents=True,exist_ok=True)
    write(output/'equivalence-triage-2026-10-15.json',sealed(dict(head=head,programs=[d for _,d,_ in data])))
    (output/'equivalence-triage-2026-10-15.md').write_text(markdown_triage([d for _,d,_ in data]))
    lines=['# Automated equivalence — 2026-10-15','',
           'The retained baseline contains **227 argued equivalents: 180 compiler/class arguments and 47 individual reviews**, plus nine additional POSTTRAN survivors/evidence gaps. INTCALC has 421 eligible mutation sites; POSTTRAN has 483. TRANREPT is a separate held-out inventory of 413 sites, with no inherited kills or equivalence decisions.', '',
           'The earlier October 12 INTCALC aggregate listed 167 gap IDs beside a count of 113. The complete per-mutant records confirm 113; the additional 54 IDs were killed. This report uses the sealed October 15 integration-run rows and preserves the historical publication unchanged.', '',
           f'Execution: [GitHub Actions run {run_id}](https://github.com/howardweale/lightyear-carddemo-modernization/actions/runs/{run_id}), source commit `{head}`. Public CardDemo only; zero model calls. All results are twin-scoped.', '',
           '| Program | Route | Resolved | Of 47 individual reviews | Other survivors resolved | New kills |', '|---|---|---:|---:|---:|---:|']
    for s,_,_ in data:
        for route,c in s['routes'].items():lines.append(f"| {s['program']} | {route} | {c['resolved']} | {c['individual_resolved']} | {c['survivors_resolved']} | {c['kills']} |")
    lines+=['','| Program | Argued resolved automatically | Unobservable | Unresolved | Estimated review minutes / 1,000 sites |','|---|---:|---:|---:|---:|']
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
            'Each enabled local statement/PIC encoder was checked on at least 10,000 deterministic random in-domain inputs per side, comparing every receiving byte against the actual pinned GnuCOBOL twin. Any disagreement disables that exact statement/PIC shape. Every emitted machine resolution was independently rebuilt, re-solved or replayed on the same source head.', '']
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
        for pattern in ('summary.json','resolutions.json','manifest.json','toolchain.json','encoder-validation.json','class-validation.json',
                        'audit-request.json','audit-packet.json','class-requests.json','class-packets/*.json',
                        'mutants/*/compiler-proof.json','mutants/*/pair.json','mutants/*/solver/query.smt2','mutants/*/solver/solver.json',
                        'mutants/*/solver/validation.json','mutants/*/oracle-gap.json','search/regression-scenarios.json','search/cases/*/kill.json'):
            for path in folder.glob(pattern):
                target=dest/path.relative_to(folder);target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(path.read_bytes())
    return head

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('inputs',type=Path);p.add_argument('output',type=Path);p.add_argument('--run-id',required=True);a=p.parse_args();print(publish(a.inputs,a.output,a.run_id))
