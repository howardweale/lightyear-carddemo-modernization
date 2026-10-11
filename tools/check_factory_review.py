"""Bounded public engineering review campaign, without containers or model calls."""
import argparse,json,subprocess
from collections import Counter
from pathlib import Path
from lightyear_mainframe.legacy_twin import ROOT,PROGRAMS,build,run,new_output,write_json,receipt,execute,FLAGS
from lightyear_mainframe.scenario_generation import manifest
from lightyear_mainframe.systematic_mutation import generate,outcome
from lightyear_mainframe.io_faults import declarations
from lightyear_mainframe.scenario_coverage import observe
from lightyear_mainframe.mutant_equivalence import argument
from lightyear_mainframe.scenario_coverage import code


def attempt(target,case,folder):
    try:
        r=run(target,case,folder,generated=case,timeout=4)
        return dict(status='executed',returncode=r['returncode'],outputs=r['outputs'],stdout_sha256=r['program_stdout_sha256'],stderr_sha256=r['program_stderr_sha256'])
    except (ValueError,RuntimeError,subprocess.TimeoutExpired,OSError) as e:
        return dict(status='execution-refusal',error_type=type(e).__name__,detail=str(e))



def fault_case(job,fault):
    case='posttran-missing-card' if fault['file']=='FD-REJS-RECORD' else 'intcalc-two-accounts' if job=='INTCALC' else 'posttran-positive'
    if job=='INTCALC' and fault['line']==444:case='intcalc-missing-disclosure'
    if job=='POSTTRAN' and fault['line']==510:case='posttran-new-category'
    return case


def relevant_faults(mutant, inv, rows):
    # Same source paragraph activates a handler mutation. Storage/display/abend
    # survivors also see representative normal, extended and INVALID statuses.
    lines=sorted(p['line'] for p in inv['paragraphs'])
    def paragraph(n):return max((p for p in lines if p<=n),default=0)
    caller_scope=paragraph(mutant['line']) if not mutant.get('source_path') else 0
    scope=caller_scope
    if mutant['operator']=='skip-PERFORM':
        words=code(mutant['original']).split()
        target=words[1].rstrip('.') if len(words)>1 else ''
        scope=next((p['line'] for p in inv['paragraphs'] if p['name']==target),scope)
    selected=[r for r in rows if paragraph(r['declaration']['line'])==scope]
    if not selected and scope!=caller_scope:
        # Error-report/abend helpers contain no I/O operation of their own.
        # Activate their call site using the caller's declared fault.
        selected=[r for r in rows if paragraph(r['declaration']['line'])==caller_scope]
    if not selected:
        selected=[r for r in rows if r['declaration']['kind'] in ('missing','extended-read-error','rewrite-error')]
    # At most one of each status/site family, three bounded derived builds.
    seen=set();result=[]
    for row in selected:
        key=row['declaration']['expected_status']
        if key in seen or not row.get('expectation_met'):continue
        seen.add(key);result.append(row)
    return result[:3]

def measure_binary_layout(output):
    folder=output/'binary-layout';folder.mkdir()
    source="""identification division.
program-id. layout-probe.
data division.
working-storage section.
01 a pic s9(9) binary.
01 b pic s9(8) binary.
01 c pic s9(4) binary.
01 d pic s9(3) binary.
procedure division.
 display function length(a) ' ' function length(b) ' '
         function length(c) ' ' function length(d)
 stop run.
"""
    (folder/'layout.cob').write_text(source)
    execute(['cobc','-x','-free',*FLAGS,'layout.cob','-o','layout'],folder,folder/'compile')
    actual=execute([folder/'layout'],folder,folder/'run').stdout.decode().split()
    result=dict(zip(('S9(9)','S9(8)','S9(4)','S9(3)'),map(int,actual)))
    write_json(folder/'measured.json',result)
    return result


def measure_runtime_contract(output):
    from hashlib import sha256
    path=Path('/usr/lib/x86_64-linux-gnu/libcob.so.4.1.0')
    value=dict(package='3.1.2-5.1ubuntu1',library_sha256=sha256(path.read_bytes()).hexdigest())
    write_json(output/'runtime-contract.json',value)
    return value


def measure_storage_semantics(output):
    folder=output/'storage-semantics';folder.mkdir()
    source="""identification division.
program-id. storage-probe.
data division.
working-storage section.
01 u pic 9(4) binary.
01 ux redefines u.
  05 ul pic x.
  05 ur pic x.
01 v pic 9(3) binary.
01 timing pic s9(9) binary.
01 timing-frac pic s9(9)v9 binary.
01 merchant-n pic 9(9).
01 merchant-x pic x(50).
01 hits pic 9(4) value 0.
01 maximum pic 9(4) value 0.
01 base pic 9(4).
01 i pic s9(9) comp.
procedure division.
 display 'LENGTHS ' function length(u) ' ' function length(v)
         ' ' function length(timing) ' ' function length(timing-frac)
 if u = 0 and timing = 0 and merchant-n = 0 and merchant-x = spaces
     display 'DEFAULTS-OK'
 end-if
 perform varying i from 1 by 1 until i > 256
     move 0 to u
     move function char(i) to ur
     move u to base
     if u > maximum move u to maximum end-if
     move 1 to u
     move function char(i) to ur
     if u = base add 1 to hits end-if
     move -1 to u
     move function char(i) to ur
     if u = base add 1 to hits end-if
 end-perform
 display 'OVERLAY ' hits ' ' maximum
 stop run.
"""
    (folder/'storage.cob').write_text(source)
    execute(['cobc','-x','-free',*FLAGS,'storage.cob','-o','storage'],folder,folder/'compile')
    lines=execute([folder/'storage'],folder,folder/'run').stdout.decode().splitlines()
    lengths=next(x.split()[1:] for x in lines if x.startswith('LENGTHS '))
    overlay=next(x.split()[1:] for x in lines if x.startswith('OVERLAY '))
    result=dict(unsigned_lengths=list(map(int,lengths[:2])),timing_lengths=list(map(int,lengths[2:])),
                initial_defaults='DEFAULTS-OK' in lines,overlay_equalities=int(overlay[0]),overlay_maximum=int(overlay[1]))
    write_json(folder/'measured.json',result)
    return result


def check(output,job):
    output=new_output(output);program=PROGRAMS[job];text=(ROOT/f'spec/mainframe/public-source/{program}.cbl').read_text()
    build(output/'baseline',instrument=True,jobs=[job]);compiler_layout=measure_binary_layout(output);storage=measure_storage_semantics(output);runtime=measure_runtime_contract(output);cases=[s['id'] for s in manifest() if s['job']==job]
    baselines={};streams=[]
    from lightyear_mainframe.legacy_twin import PUBLIC_SCENARIOS
    for public,(scope,_) in PUBLIC_SCENARIOS.items():
        if scope!=job:continue
        folder=output/'public'/public;folder.parent.mkdir(exist_ok=True)
        run(output/'baseline',public,folder)
        streams.append((folder/'logs/program.stdout').read_text())
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
            case=fault_case(job,fault)
            actual=attempt(folder/'build',case,folder/'run')
            stdout=folder/'run/logs/program.stdout';stderr=folder/'run/logs/program.stderr'
            transcript=(stdout.read_text() if stdout.exists() else '')+(stderr.read_text() if stderr.exists() else '')
            if stdout.exists():streams.append(stdout.read_text())
            display=fault['expected_display'];display_ok=not display or display in transcript
            if display=='LYF-REASON=109':display_ok='LYF-REASON=000000109' in transcript or 'LYF-REASON=109' in transcript
            matched=actual.get('returncode')==fault['expected_returncode'] and display_ok and f"LYF|{fault['id']}|{fault['expected_status']}" in transcript
            faults.append(dict(declaration=fault,actual=actual,expectation_met=matched,coverage=observe(inv,transcript)))
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
            if record['status']=='survived':
                record['fault_challenges']=[]
                for fault_row in relevant_faults(mutant,inv,faults):
                    fault=fault_row['declaration'];case=fault_case(job,fault)
                    challenge=folder/('fault-'+fault['id']);challenge.mkdir()
                    attempt_row=dict(fault=fault['id'],case=case)
                    try:
                        build(challenge/'build',systematic=mutant,fault=fault['id'],jobs=[job])
                        changed=attempt(challenge/'build',case,challenge/'run')
                        classification=outcome(fault_row['actual'],changed)
                        attempt_row.update(status=classification,actual=changed)
                        if classification!='survived':
                            record.update(status=classification,killed_by='fault:'+fault['id']+':'+case,actual=changed,baseline=fault_row['actual'])
                    except (ValueError,RuntimeError) as e:
                        # An incompatible seam/compile is not a killed original
                        # mutant; its normal compilation/survival is preserved.
                        attempt_row.update(status='fault-challenge-unavailable',detail=str(e))
                    record['fault_challenges'].append(attempt_row)
                    if record['status']!='survived':break
            if record['status']=='survived':
                proof=argument(text,program,mutant,compiler_layout,storage,runtime)
                if proof:record.update(status='equivalent (argued, listed)',disposition=proof)
                else:record['disposition']='unresolved: no equivalence claim; requires additional scenario or reviewed proof'
        results.append(record);write_json(output/'mutation-results.json',results)
    # Each demonstrated mutant kill keeps its exact scenario/fault witness;
    # a greedy coverage selector may not drop it merely for adding no branch.
    selected=sorted({r['killed_by'] for r in results if r['killed_by']})
    write_json(output/'systematic-scenario-selection.json',dict(
        policy='retain-every-demonstrated-systematic-kill-witness',selected=selected,
        mutant_witnesses={r['id']:r['killed_by'] for r in results if r['killed_by']},
        unresolved=[r['id'] for r in results if r['status']=='survived']))
    counts=Counter(r['status'] for r in results);after=observe(inv,'\n'.join(streams))
    summary=receipt(output/'review-summary.json',phase='factory-review-engineering',job=job,before_faults=before,after_faults=after,
        compiler_binary_layout=compiler_layout,compiler_storage_semantics=storage,compiler_runtime_contract=runtime,fault_count=len(faults),fault_expectations_met=sum(r.get('expectation_met',False) for r in faults),mutant_count=len(mutants),mutation_counts=dict(counts),
        kill_rate=f"{counts['killed-divergent']+counts['killed-failure']}/{len(mutants)}",excluded_equivalents=[r for r in results if r['status']=='equivalent (argued, listed)'],
        eligible_kill_rate=f"{counts['killed-divergent']+counts['killed-failure']}/{len(mutants)-counts['equivalent (argued, listed)']}",
        unresolved_survivors=[r['id'] for r in results if r['status']=='survived'],
        retained_killing_scenarios=sorted({r['killed_by'] for r in results if r['killed_by']}),model_calls=0,
        limitation='Systematic pinned-source mutation; survivors and compiler refusals block adequacy. Public engineering, not z/OS equivalence.')
    print(json.dumps(summary,indent=2))
    if not all(r.get('expectation_met') for r in faults):raise AssertionError('declared fault expectation mismatch; preserved actual outcomes')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('output',type=Path);p.add_argument('job',choices=PROGRAMS);a=p.parse_args();check(a.output,a.job)
