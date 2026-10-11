"""Reproduce Howard's dated decision overlay and seeded independent-review packet.

Reads public, historical evidence; never compiles, runs models or authorizes release.
"""
import argparse
import json
from hashlib import sha256
from pathlib import Path
from lightyear_mainframe.systematic_mutation import generation_inventory
from lightyear_factory.scenario_policy import IO_ACCEPTANCES

SEED='Howard-2026-10-11-equivalence-review-20-v1'
PROGRAMS={'INTCALC':'CBACT04C','POSTTRAN':'CBTRN02C'}


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()


def digest(value):return sha256(canonical(value)).hexdigest()


def select(population,program,seed=SEED,n=10):
    if len({r['id'] for r in population})!=len(population):raise ValueError('duplicate-mutant')
    if len(population)<n:raise ValueError('insufficient-population')
    # Uniform pseudorandom hash ordering, no replacement; ID breaks hash ties.
    def rank(row):return (sha256((seed+'\0'+program+'\0'+row['id']).encode()).hexdigest(),row['id'])
    return sorted(population,key=rank)[:n]


def build(root):
    directory=root/'docs/factory';inputs={}
    def read(name):
        data=(directory/name).read_bytes();inputs[name]=sha256(data.replace(b'\r\n',b'\n')).hexdigest()
        return json.loads(data)
    historical=read('systematic-review311-summary.json')
    additional=read('post-campaign-equivalence-review311.json')['arguments']
    arguments=read('io-gap-arguments.json')
    packet=dict(schema='factory-equivalence-independent-review/1',seed=SEED,
        selection='Lowest ten SHA-256(seed + NUL + program + NUL + mutant ID), ID tie-break; without replacement from all listed arguments.',
        independent_review_status='pending',threshold_approved=False,programs={})
    report=dict(schema='factory-howard-decisions/1',decided_by='Howard',decided_on='2026-10-11',
        authority='Explicit user chat decisions; documentation of acceptance, not a cryptographic approval receipt.',
        threshold_approved=False,release_approved=False,
        compiler_policy='List compiler refusals and exclude from adequacy denominators; they are neither kills nor blockers.',
        eof_exceptions=[],programs={})
    for acceptance,gap in zip(IO_ACCEPTANCES,arguments['gaps']):
        gap_id=gap.get('outcome_id',gap.get('id'))
        if acceptance['id']!=gap_id or acceptance['source_sha256']!=gap['source_sha256']:
            raise ValueError('EOF-argument-binding')
        report['eof_exceptions'].append(dict(acceptance,argument=gap['argument'],
            argument_record_sha256=digest(gap),measured_coverage_unchanged=True))
    for job,program in PROGRAMS.items():
        data=read(f'systematic-{job.lower()}-review311.json');rows=data['mutants'];summary=historical['programs'][job]
        text=(root/f'spec/mainframe/public-source/{program}.cbl').read_text(encoding='utf-8')
        if sha256(text.encode()).hexdigest()!=summary['source_sha256']:raise ValueError('program-source-binding')
        generation=generation_inventory(text,program)
        post={r['id']:r for r in additional if r['id'].startswith(program+'-')}
        population=[]
        for row in rows:
            proof=row.get('disposition') if row['status']=='equivalent (argued, listed)' else post.get(row['id'])
            if not isinstance(proof,dict):continue
            if not proof.get('argument'):raise ValueError('missing-argument')
            if proof['source_sha256']!=row['source_sha256']:raise ValueError('argument-source-binding')
            source_path='spec/mainframe/copybooks/'+row['source_path'] if row.get('source_path') else f'spec/mainframe/public-source/{program}.cbl'
            source=(root/source_path).read_text(encoding='utf-8')
            if sha256(source.encode()).hexdigest()!=row['source_sha256']:raise ValueError('mutant-source-binding')
            population.append(dict(id=row['id'],operator=row['operator'],line=row['line'],end_line=row['end_line'],
                source_path=source_path,source_sha256=row['source_sha256'],program_sha256=summary['source_sha256'],
                original=row['original'],replacement=row['replacement'],historical_status=row['status'],
                argument_origin='inline' if row['status']=='equivalent (argued, listed)' else 'post-campaign',
                argument=proof,raw_mutant_record_sha256=digest(row)))
        population.sort(key=lambda x:x['id'])
        chosen=[dict(r,independent_review=dict(status='pending',reviewer=None,date=None,findings=None)) for r in select(population,program)]
        packet['programs'][job]=dict(program=program,population_count=len(population),
            population_sha256=digest(population),population_ids=[r['id'] for r in population],sample=chosen)
        refused=[dict(id=r['id'],line=r['line'],source_sha256=r['source_sha256'],compiler_diagnostic=r['compiler_diagnostic']) for r in rows if r['status']=='not-compiled']
        killed=sum(r['status'].startswith('killed-') for r in rows)
        eligible=len(rows)-len(population)-len(refused)
        report['programs'][job]=dict(program=program,raw_generated=len(rows),raw_killed=killed,
            raw_kill_fraction=f'{killed}/{len(rows)}',listed_argued_equivalents=len(population),
            compiler_refusal_count=len(refused),compiler_refusals=refused,eligible_count=eligible,
            conditional_eligible_kill_fraction=f'{killed}/{eligible}',
            condition='Listed equivalence arguments await independent review; this is not threshold approval.',
            generator_avoided_count=generation['avoided_count'],generator_retained_count=len(generation['candidates']),
            generator_avoided=generation['avoided'],
            generator_validation='Static source checks prevent these sites; no new compiled campaign claimed.',
            recorded_io_fraction=summary['after_faults']['coverage_by_class']['io-handling']['fraction'],
            accepted_unobserved_io_exceptions=1)
    packet['input_lf_sha256']=dict(inputs);report['input_lf_sha256']=dict(inputs)
    fault=read('fault-posttran-review311.json')
    rewrite=next(r for r in fault['faults'] if r['declaration']['line']==554)
    if rewrite['actual_returncode']!=0:raise ValueError('rewrite-observation-changed')
    register=dict(schema='factory-keep-or-fix-register/1',decision_by='Howard',decision_date='2026-10-11',
        default_conversion_policy='Preserve recorded legacy behavior. A fix requires a separate explicit behavior-change decision.',
        defects=[dict(id='REWRITE-109',program='CBTRN02C',source_sha256=historical['programs']['POSTTRAN']['source_sha256'],
            source_lines=[211,212,213,214,215,424,554,555,556,557,558,559,560,562,564],
            classification='legacy-defect-not-twin-defect',disposition='keep-by-default',
            observed_behavior='Injected account REWRITE status23 enters INVALID KEY, sets reason109 and ACCOUNT RECORD NOT FOUND, returns to posting and writes the transaction. The compiled fault case returned0, with no subsequent reject-path selection for109.',
            evidence='docs/factory/fault-posttran-review311.json',evidence_lf_sha256=inputs['fault-posttran-review311.json'],
            evidence_record_sha256=digest(rewrite),fix_authorized=False),
        dict(id='CBACT04C-FINAL-ACCOUNT-EOF-ELSE',program='CBACT04C',source_sha256=historical['programs']['INTCALC']['source_sha256'],
            source_lines=[137,188,189,190,191,194,195,196,219,220,222,340,350,352,353,354,356],
            classification='legacy-defect-not-twin-defect',disposition='keep-by-default',
            observed_behavior='The final-account PERFORM1050 at220 is in the outer EOF ELSE. TEST BEFORE loop entry requires EOF=N; the final READ setsY inside the true branch and exits on the next loop test. Thus this final flush is not executed. Earlier accounts flush on account change at196; the last account is not flushed by the EOF ELSE. Recorded I/O coverage leaves the189 false edge unobserved.',
            evidence='docs/factory/io-gap-arguments.json',evidence_lf_sha256=inputs['io-gap-arguments.json'],
            supporting_campaign='docs/factory/systematic-review311-summary.json',fix_authorized=False)])
    return packet,report,register


def render(packet):
    lines=['# Independent review: 20 argued-equivalent mutants','',
        'Howard requested this review on 2026-10-11. Ten mutants per program were drawn from the complete listed argument population. Selection was not rerolled. Review findings are pending; scenario-threshold/2 remains unapproved.','',
        f"Seed: `{packet['seed']}`. Algorithm: {packet['selection']}",'',
        'Review each argument against the pinned source and runtime scope. Record accept/reject/needs-evidence, reviewer, date and reasons. Acceptance of EOF exceptions or legacy behavior does not approve these equivalence arguments.','']
    for job,group in packet['programs'].items():
        lines += [f"## {job}: 10 of {group['population_count']}",'',f"Population SHA-256: `{group['population_sha256']}`",'']
        for row in group['sample']:
            proof=row['argument']
            lines += [f"### {row['id']}",'',f"Source: `{row['source_path']}` lines {row['line']}â€“{row['end_line']}; SHA-256 `{row['source_sha256']}`.",'',
                f"Historical status: {row['historical_status']}; argument origin: {row['argument_origin']}.",'',
                'Original:','```cobol',row['original'].rstrip(),'```','Replacement:','```cobol',row['replacement'],'```','',
                proof['argument'],'',f"Supporting source lines: {proof.get('supporting_source_lines', [])}.",'']
            for key in ('scope','compiler_runtime_contract','runtime_source_argument','runtime_original_source_sha256'):
                if key in proof:lines += [f"{key}: {proof[key]}",'']
            lines += ['Independent finding: **pending**. Reviewer / date / reasons: ____________________','']
    lines += ['Machine-readable packet: [equivalence-review-sample-2026-10-11.json](equivalence-review-sample-2026-10-11.json). It includes all population IDs, input hashes, full arguments and raw-record hashes.','']
    return '\n'.join(lines)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1]);args=parser.parse_args()
    packet,report,register=build(args.root);folder=args.root/'docs/factory'
    for name,value in [('equivalence-review-sample-2026-10-11.json',packet),('howard-decisions-2026-10-11.json',report),('keep-or-fix-register.json',register)]:
        (folder/name).write_text(json.dumps(value,indent=2,sort_keys=True)+'\n',encoding='utf-8',newline='\n')
    (folder/'equivalence-review-sample-2026-10-11.md').write_text(render(packet),encoding='utf-8',newline='\n')

if __name__=='__main__':main()
