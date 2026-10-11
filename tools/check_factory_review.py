"""Bounded public engineering review campaign, without containers or model calls."""
import argparse,json,subprocess
from collections import Counter
from pathlib import Path
from lightyear_mainframe.legacy_twin import ROOT,PROGRAMS,build,run,new_output,write_json,receipt
from lightyear_mainframe.scenario_generation import manifest
from lightyear_mainframe.systematic_mutation import generate,outcome
from lightyear_mainframe.io_faults import declarations
from lightyear_mainframe.scenario_coverage import observe


def attempt(target,case,folder):
    try:
        r=run(target,case,folder,generated=case,timeout=4)
        return dict(status='executed',returncode=r['returncode'],outputs=r['outputs'],stdout_sha256=r['program_stdout_sha256'])
    except (ValueError,RuntimeError,subprocess.TimeoutExpired,OSError) as e:
        return dict(status='execution-refusal',error_type=type(e).__name__,detail=str(e))


def check(output,job):
    output=new_output(output);program=PROGRAMS[job];text=(ROOT/f'spec/mainframe/public-source/{program}.cbl').read_text()
    build(output/'baseline',instrument=True,jobs=[job]);cases=[s['id'] for s in manifest() if s['job']==job]
    baselines={};streams=[]
    for case in cases:
        folder=output/'cases'/case;folder.parent.mkdir(exist_ok=True)
        baselines[case]=attempt(output/'baseline',case,folder)
        log=folder/'logs/program.stdout'
        if log.exists():streams.append(log.read_text())
    inv=json.loads((output/'baseline'/job/'coverage-inventory.json').read_text());before=observe(inv,'\n'.join(streams))
    faults=[]
    for fault in declarations(text,program):
        folder=output/'faults'/fault['id'];folder.mkdir(parents=True)
        try:
            build(folder/'build',fault=fault['id'],jobs=[job])
            # A rejected transaction is needed to reach the rejects WRITE.
            case='posttran-missing-card' if fault['file']=='FD-REJS-RECORD' else 'intcalc-two-accounts' if job=='INTCALC' else 'posttran-positive'
            if job=='INTCALC' and fault['line']==444:case='intcalc-missing-disclosure'
            if job=='POSTTRAN' and fault['line']==510:case='posttran-new-category'
            actual=attempt(folder/'build',case,folder/'run')
            stdout=folder/'run/logs/program.stdout';stderr=folder/'run/logs/program.stderr'
            transcript=(stdout.read_text() if stdout.exists() else '')+(stderr.read_text() if stderr.exists() else '')
            if stdout.exists():streams.append(stdout.read_text())
            display=fault['expected_display'];display_ok=not display or display in transcript
            if display=='LYF-REASON=109':display_ok='LYF-REASON=000000109' in transcript or 'LYF-REASON=109' in transcript
            matched=actual.get('returncode')==fault['expected_returncode'] and display_ok and f"LYF|{fault['id']}|{fault['expected_status']}" in transcript
            faults.append(dict(declaration=fault,actual=actual,expectation_met=matched))
        except (RuntimeError,ValueError) as e:faults.append(dict(declaration=fault,status='not-compiled',detail=str(e)))
        write_json(output/'fault-results.json',faults)
    mutants=generate(text,program);write_json(output/'mutation-inventory.json',mutants);results=[]
    for mutant in mutants:
        folder=output/'mutants'/mutant['id'];folder.mkdir(parents=True)
        record=dict(id=mutant['id'],operator=mutant['operator'],line=mutant['line'],status='survived',killed_by=None)
        try:build(folder/'build',systematic=mutant,jobs=[job])
        except (RuntimeError,ValueError) as e:record.update(status='not-compiled',detail=str(e))
        else:
            for case in cases:
                baseline=baselines[case]
                if baseline['status']!='executed':continue
                changed=attempt(folder/'build',case,folder/case);classification=outcome(baseline,changed)
                if classification!='survived':
                    record.update(status=classification,killed_by=case,actual=changed,baseline=baseline);break
            if record['status']=='survived':record['disposition']='unresolved: no equivalence claim; requires additional scenario or reviewed proof'
        results.append(record);write_json(output/'mutation-results.json',results)
    counts=Counter(r['status'] for r in results);after=observe(inv,'\n'.join(streams))
    summary=receipt(output/'review-summary.json',phase='factory-review-engineering',job=job,before_faults=before,after_faults=after,
        fault_count=len(faults),fault_expectations_met=sum(r.get('expectation_met',False) for r in faults),mutant_count=len(mutants),mutation_counts=dict(counts),
        kill_rate=f"{counts['killed-divergent']+counts['killed-failure']}/{len(mutants)}",excluded_equivalents=[],
        unresolved_survivors=[r['id'] for r in results if r['status']=='survived'],
        retained_killing_scenarios=sorted({r['killed_by'] for r in results if r['killed_by']}),model_calls=0,
        limitation='Systematic pinned-source mutation; survivors and compiler refusals block adequacy. Public engineering, not z/OS equivalence.')
    print(json.dumps(summary,indent=2))
    if not all(r.get('expectation_met') for r in faults):raise AssertionError('declared fault expectation mismatch; preserved actual outcomes')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('output',type=Path);p.add_argument('job',choices=PROGRAMS);a=p.parse_args();check(a.output,a.job)
