"""Prepare six unsigned requests. The final effective request remains fail-closed."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess

from lightyear_control_tower.decisions import digest
from lightyear_control_tower.threshold_conditions import CONDITIONS


def build(root, output, prepared_on="2026-10-17"):
    root,output=Path(root),Path(output);output.mkdir(parents=True,exist_ok=True)
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
    def read(path):return json.loads((root/path).read_bytes())
    def source(path):
        raw=(root/path).read_bytes()
        if subprocess.check_output(['git','show',head+':'+path],cwd=root)!=raw:raise ValueError('signing-source-not-committed')
        return dict(path=path,sha256=sha256(raw).hexdigest(),commit=head)
    base='docs/factory/release-evidence-2026-10-15/'
    review_path=base+'aggregate/INTCALC/results.json';summary_path=base+'aggregate/INTCALC/summary.json'
    register_path='docs/factory/keep-or-fix-register.json';policy_path='docs/factory/scenario-threshold-3-proposal-2026-10-15.json'
    reviews=read(review_path);summary=read(summary_path);policy=read(policy_path)['proposed_policy']
    sources=[source(p) for p in (review_path,summary_path,register_path,policy_path,base+'index.json')]
    conditions=[dict(condition_sha256=sha256(text.encode()).hexdigest(),state='not-met',evidence=None) for text in CONDITIONS]
    def contract(kind,details,extra=()):return dict(schema='factory-contract/1',kind=kind,program='INTCALC',sources=sources+list(extra),details=details)
    domain='docs/factory/intcalc-duplicate-category-proposal-2026-10-12.json'
    proposal=read(domain)
    generator=next(r for r in proposal['bound_sources'] if r['path'].endswith('/scenario_generation.py'))
    generator_raw=(root/generator['path']).read_bytes().replace(b'\r\n',b'\n')
    if sha256(generator_raw).hexdigest()!=generator['lf_sha256']:raise ValueError('loader-generator-changed')
    generator_lines=[i for i,line in enumerate(generator_raw.decode().splitlines(),1) if "'duplicate-category'" in line]
    if not generator_lines:raise ValueError('loader-generator-scenario-missing')
    class_ids=sorted(r['id'] for r in reviews if r.get('class_covered'))
    individual_ids=sorted(r['id'] for r in reviews if r['status'] in ('equivalent (argued, individual review pending)','equivalent (compiler-proven)'))
    if len(class_ids)!=81 or len(individual_ids)!=32:raise ValueError('review-inventory-changed')
    class_details=dict(packet_sha256=digest(reviews),items=class_ids,class_proof_sha256=summary['class_census'],
        reviewer_type='AI-assisted',claim_scope='twin',dependencies=[])
    dependencies=sorted({d['id'] for r in reviews if r['id'] in individual_ids for d in r.get('argument',{}).get('depends_on_register',[])})
    thresholds=dict(policy_sha256=digest(policy),version='scenario-threshold/3',effective_condition='conditions-pending',
        compiler_refusals='listed-excluded-not-blockers',conditions=conditions,evidence_head=summary['current_head'],required_review_ids=individual_ids)
    io_path='docs/factory/io-gap-arguments.json'
    gap=next(r for r in read(io_path)['gaps'] if r['program']=='CBACT04C')
    records=[
        ('01-loader-domain',contract('legacy-behaviour-disposition',dict(entry_id='INTCALC-DUPLICATE-CATEGORY-LOADER-DOMAIN',
            source_sha256=generator['lf_sha256'],lines=generator_lines,observed_behaviour_sha256=proposal['content_sha256'],
            dependent_arguments=sorted(r['id'] for r in reviews)),[source(domain)])),
        ('02-appl-result-class',contract('equivalence-review',class_details)),
        ('03-individual-and-compiler',contract('equivalence-review',dict(class_details,items=individual_ids,class_proof_sha256=None,dependencies=dependencies))),
        ('04-threshold3-policy',contract('scenario-threshold-approval',thresholds)),
        ('05-line189-io',contract('io-exception-acceptance',dict(source_sha256=gap['source_sha256'],line=189,outcome='false',
            outcome_id=gap['outcome_id'],argument_sha256=digest(gap),basis='structurally-unreachable'),[source(io_path)])),
        ('06-effective-threshold-last',contract('scenario-threshold-approval',dict(thresholds,effective_condition='unconditional')))]
    from lightyear_control_tower.factory_order import body_hash
    hashes=[body_hash(value) for _,value in records]
    packet=digest(hashes)
    items=[]
    for position,(name,value) in enumerate(records,1):
        value['signing_order']=dict(packet_sha256=packet,position=position,
            predecessor_contract_sha256=hashes[position-2] if position>1 else None,predecessor_decision_sha256=None)
        filename='intcalc-'+name+'-request-'+prepared_on+'.json'
        raw=(json.dumps(value,indent=2,sort_keys=True)+'\n').encode();(output/filename).write_bytes(raw)
        items.append(dict(order=len(items)+1,path='docs/factory/'+filename,sha256=sha256(raw).hexdigest(),kind=value['kind'],
            signable_prerequisites_complete=False if name.startswith('06') else None))
    index=dict(schema='factory-unsigned-signing-order/1',prepared_on=prepared_on,program='INTCALC',claim_scope='twin',items=items,
        effective=False,signed=False,release_authorized=False,
        blocker='Final effective request intentionally refuses: all four typed conditions must be re-bound to real evidence, including trusted signed review proofs. The current evidence is provisional engineering evidence; signatures cannot change that scope.',
        next_step='All six files are unsigned templates. Requests 02–06 are not importable until their predecessor decision hash is bound and verified against the externally trusted Factory journal. Rebuild typed conditions from real evidence; never mark missing proofs met by hand. No signing is authorized by this inventory.')
    (output/('intcalc-signing-order-'+prepared_on+'.json')).write_text(json.dumps(index,indent=2)+'\n',encoding='utf-8')
    return index


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('output');p.add_argument('--root',default='.')
    a=p.parse_args();build(a.root,a.output)
