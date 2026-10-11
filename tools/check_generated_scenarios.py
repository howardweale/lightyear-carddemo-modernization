"""Public generated scenarios: real twins, INTCALC three-way, POSTTRAN invariants."""
import argparse
from collections import defaultdict
import json
import os
from pathlib import Path
from lightyear_mainframe.legacy_twin import build,run,new_output,receipt,write_json,FILES,PUBLIC_SCENARIOS,sha,execute,ROOT
from lightyear_mainframe.scenario_generation import manifest,case,MUTANTS
from lightyear_mainframe.scenario_coverage import observe
from lightyear_mainframe.twin_reconciliation import compile_java,reference,compare_images
from lightyear_mainframe.records import load_copybook,from_ascii_fixed
from lightyear_mainframe.zos_bindings import load_bindings,dataset_binding


def run_case(build_dir,name,out,generated=False):
    try:
        r=run(build_dir,name,out,generated=name if generated else None)
        return dict(status='executed',returncode=r['returncode'],outputs=r['outputs'],
                    scenario_adequacy=r['scenario_adequacy'],invariants=r['invariants'],receipt=r['content_sha256'])
    except (RuntimeError,ValueError) as e:
        # Preserve an actual refusal, never count compilation/setup failure as a kill.
        out.mkdir(parents=True,exist_ok=True)
        write_json(out/'campaign-refusal.json',{'error_type':type(e).__name__,'detail':str(e)})
        return dict(status='refused',reason=str(e))


def signature(r):
    return {k:r.get(k) for k in ('status','returncode','outputs')}


def three_way(meta,images,folder,twin,java):
    inputs=folder/'compare-inputs';inputs.mkdir()
    for dd,raw in images.items():(inputs/dd).write_bytes(raw)
    try:py=reference(meta,images,folder/'python')
    except Exception as e:
        py=dict(status='execution-failure',error_type=type(e).__name__,detail=str(e))
        write_json(folder/'python-refusal.json',py)
    (folder/'java').mkdir()
    r=execute([str(Path(os.environ['JAVA_HOME'])/'bin/java'),'-cp',java/'classes','TwinCandidate',inputs,folder/'java',
               meta['processing_date'],meta['candidate_timestamp']],folder,folder/'java/run',allowed=(0,1))
    states=dict(twin=signature(twin),python=py,java_returncode=r.returncode)
    complete=twin['status']=='executed' and twin['returncode']==0 and py['status']=='completed' and r.returncode==0
    comparisons={}
    if complete:
        for dd in ('ACCTFILE','TRANSACT'):
            binding=dataset_binding(load_bindings(),'INTCALC','STEP15',dd);layout=load_copybook(ROOT/binding['copybook'])
            paths={'twin':folder/'traced/after'/dd,'python':folder/'python'/dd,'java':folder/'java'/dd}
            for left,right in (('twin','python'),('twin','java'),('python','java')):
                comparisons[left+'-'+right+'-'+dd]=compare_images(paths[left].read_bytes(),paths[right].read_bytes(),layout,binding['keys'])
    agrees=complete and all(x['byte_identical'] for x in comparisons.values())
    return dict(states=states,comparisons=comparisons,status='byte-agreement' if agrees else 'unresolved',
                auto_repair=False,adjudication='required' if not agrees else 'none')


def check(output):
    output=new_output(output);build(output/'control');build(output/'traced',instrument=True)
    java=output/'java-build';compile_java(java)
    cases=manifest();write_json(output/'generator-manifest.json',cases)
    mutants={}
    for name,(job,_,_) in MUTANTS.items():
        try:build(output/name,mutant=name);mutants[name]={'job':job,'build':'compiled','killed_by':[]}
        except (RuntimeError,ValueError) as e:mutants[name]={'job':job,'build':'incompetent','reason':str(e),'killed_by':[]}
    rows=[];seen={job:set() for job in ('INTCALC','POSTTRAN')}; killed=set();all_stdout=defaultdict(list);base_stdout=defaultdict(list)
    distinct=defaultdict(lambda:defaultdict(set))
    for name,(job,_) in PUBLIC_SCENARIOS.items():
        if name not in ('intcalc-public-1','intcalc-public-2','posttran-public'):continue
        folder=output/name;folder.mkdir();r=run_case(output/'traced',name,folder/'traced')
        text=(folder/'traced/logs/program.stdout').read_text();base_stdout[job].append(text);all_stdout[job].append(text)
        seen[job].update((x['line'],x['outcome']) for x in r['scenario_adequacy']['observed_outcomes'])
    for spec in cases:
        name=spec['id'];job,meta,images,provenance=case(name);folder=output/name;folder.mkdir()
        write_json(folder/'provenance.json',provenance)
        control=run_case(output/'control',name,folder/'control',True)
        traced=run_case(output/'traced',name,folder/'traced',True)
        if control['status']!='executed' or traced['status']!='executed':
            raise AssertionError('generated control execution unavailable:'+name+':'+str(control)+':'+str(traced))
        if signature(control)!=signature(traced):raise AssertionError('generated instrumentation control differs:'+name)
        stdout=folder/'traced/logs/program.stdout'
        if stdout.exists():all_stdout[job].append(stdout.read_text())
        coverage={(x['line'],x['outcome']) for x in traced.get('scenario_adequacy',{}).get('observed_outcomes',[])}
        new_coverage=coverage-seen[job];new_kills=[];mutation_results={}
        for mutant,m in mutants.items():
            if m['job']!=job or m['build']!='compiled':continue
            changed=run_case(output/mutant,name,folder/mutant,True)
            mutation_results[mutant]=signature(changed)
            if traced['status']=='executed' and changed['status']=='executed' and signature(traced)!=signature(changed):
                m['killed_by'].append(name)
                if mutant not in killed:new_kills.append(mutant)
        selected=bool(new_coverage or new_kills);seen[job]|=coverage;killed.update(new_kills)
        row=dict(id=name,job=job,generator=spec['generator'],selected=selected,
                 selection_reason=dict(new_outcomes=len(new_coverage),new_mutant_kills=new_kills),
                 twin=traced,mutants=mutation_results)
        if job=='INTCALC':row['reconciliation']=three_way(meta,images,folder,traced,java)
        else:
            repeat=run_case(output/'control',name,folder/'repeat',True)
            row['repeatability']=signature(repeat)==signature(control)
            row['invariants']=traced.get('invariants')
            row['reconciliation']=dict(status='provisional-invariants-only',second_opinion='pending-approved-model-budget')
        if traced['status']=='executed':
            for dd in ('ACCTFILE','TRANSACT') if job=='INTCALC' else ('ACCTFILE','TRANFILE','DALYREJS','TCATBALF'):
                b=dataset_binding(load_bindings(),job,'STEP15',dd);layout=load_copybook(ROOT/b['copybook'])
                for record in from_ascii_fixed(layout,(folder/'traced/after'/dd).read_bytes()):
                    for f in record['fields']:
                        if not f['filler']:distinct[job][dd+':'+f['path']].add(str(f['value']))
        rows.append(row);write_json(folder/'comparison.json',row)
    programs={}
    for job in ('INTCALC','POSTTRAN'):
        inv=json.loads((output/'traced'/job/'coverage-inventory.json').read_text())
        baseline=observe(inv,'\n'.join(base_stdout[job]));combined=observe(inv,'\n'.join(all_stdout[job]))
        relevant=[m for m in mutants.values() if m['job']==job]
        combined['legacy_mutants_killed']=f"{sum(bool(m['killed_by']) for m in relevant)}/{len(relevant)}"
        combined['distinct_values_per_output_field']={k:len(v) for k,v in distinct[job].items()}
        combined['unsolved_outcomes']=[dict(x,solver_status='not-solved',domain='input-only public fixture generator; I/O fault outcomes not inferred') for x in combined['uncovered']]
        programs[job]=dict(public_only=baseline,public_plus_generated=combined)
    unresolved=[dict(scenario=r['id'],reason='three-way disagreement or execution refusal') for r in rows if r['reconciliation']['status']=='unresolved']
    unresolved += [dict(scenario=r['id'],reason='POSTTRAN invariant failure/refusal') for r in rows if r['job']=='POSTTRAN' and (not r['invariants'] or not r['invariants']['passed'])]
    return receipt(output/'generated-summary.json',phase='generated-scenario-campaign',programs=programs,
                   cases=rows,mutants=mutants,unresolved=unresolved,model_calls=0,
                   rounded_removal='not applicable: pinned CBACT04C has no ROUNDED; addition tested',
                   scope='finite public engineering experiment; no universal reachability proof')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('output',type=Path);check(p.parse_args().output)
