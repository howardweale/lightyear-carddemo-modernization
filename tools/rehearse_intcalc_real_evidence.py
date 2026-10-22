"""CI-only request-06 rehearsal: measured inputs and disposable test signatures.

The signed verdict is explicitly a provisional harness fixture, not a new
candidate comparison. Only an unsigned result summary is retained.
"""
import argparse
from collections import Counter
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil

from lightyear_control_tower.decisions import digest
from lightyear_control_tower.factory_order import body_hash, bind_predecessor
from lightyear_control_tower.threshold_conditions import CONDITIONS
from lightyear_factory.scenario_policy import assess, issue, release
from lightyear_factory.tower_authority import FactoryAuthority
from lightyear_mainframe.loader_domain import verify_seal
from lightyear_mainframe.zos_evidence import Signer, initialize_key
from tests.test_decision_console_factory import FactoryTests
from tools.build_intcalc_signing_requests import build

ROOT=Path(__file__).resolve().parents[1]


def measured(folder):
    read=lambda name: json.loads((folder/name).read_bytes())
    summary=verify_seal(read('summary.json'))
    threshold=verify_seal(read('threshold-2-by-scope.json')['twin'])
    projection=verify_seal(read('loader-domain-review-projection.json'))
    fresh=read('fresh-mutants.json'); reviews=read('results.json')
    head=os.environ['GITHUB_SHA']
    # PR workflows check out the PR head; the aggregate's verified provenance
    # supplies that head rather than GitHub's synthetic merge commit.
    import subprocess
    head=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    if summary['current_head']!=head or threshold['current_head']!=head or projection['head']!=head:
        raise ValueError('rehearsal-exact-head-required')
    if not all(r['passed'] for r in projection['independent_crosscheck'].values()):
        raise ValueError('rehearsal-independent-crosscheck-required')
    mutation=projection['projected_thresholds']['twin']
    excluded={r['id']:r for r in mutation['excluded_equivalents']}
    by_id={r['id']:r for r in reviews}
    if len(fresh)!=summary['expected_sites'] or len({r['id'] for r in fresh})!=len(fresh):
        raise ValueError('rehearsal-mutant-inventory')
    counts=Counter(r['status'] for r in fresh if r['id'] not in excluded)
    allowed={'killed-divergent','killed-failure','survived','not-compiled'}
    if set(counts)-allowed:raise ValueError('rehearsal-unresolved-raw-evidence')
    projected={name:counts[name] for name in allowed}
    projected['equivalent (argued, listed)']=len(excluded)
    dispositions=[]
    for identifier,row in excluded.items():
        review=by_id[identifier]
        if not review.get('argument'):raise ValueError('rehearsal-missing-source-argument')
        dispositions.append(dict(mutant_id=identifier,argument=review['argument'],
                                 source_sha256=review['mutant']['source_sha256']))
    adequacy=dict(instrumented=True,program=threshold['program'],source_sha256=threshold['source_sha256'],
        coverage_by_class={'business-logic':threshold['business'],'io-handling':threshold['io']},
        legacy_mutants_killed=mutation['kill_rate'],
        systematic_mutation=dict(counts=projected,eligible_count=mutation['eligible'],
            excluded_equivalents=len(excluded),equivalent_dispositions=dispositions,
            unresolved_survivors=[r['id'] for r in mutation['unresolved_survivors']],
            not_compiled=mutation['compiler_refusals']),
        distinct_values_per_output_field=threshold['distinct_values_per_output_field'],
        constant_field_evidence=threshold['constant_field_evidence'],
        uncovered=threshold['unaccepted_outcomes']+threshold['accepted_uncovered_IO'])
    if sum(projected.values())!=len(fresh):raise ValueError('rehearsal-mutant-denominator')
    policy=json.loads((ROOT/'docs/factory/scenario-threshold-3-proposal-2026-10-15.json').read_bytes())['proposed_policy']
    reasons=assess(adequacy,policy,threshold['compared_fields'])
    if reasons:raise ValueError('rehearsal-measured-prerequisites:'+','.join(reasons))
    return summary,threshold,adequacy,policy,head,by_id


def rehearse(folder,output):
    if os.environ.get('GITHUB_ACTIONS')!='true':raise ValueError('CI-only-disposable-signing-rehearsal')
    if os.environ.get('LIGHTYEAR_FACTORY_AUTHORITY'):raise ValueError('configured-authority-forbidden-in-rehearsal')
    folder=Path(folder);output=Path(output)
    summary,threshold,adequacy,policy,head,reviews=measured(folder)
    fixture=FactoryTests('runTest');fixture.setUp()
    try:
        fixture.service.grant_roles('howard',['operator','qualification-approver','business-owner','campaign-authorizer'],
            reason='Disposable CI request-06 rehearsal only',workloads=['factory:INTCALC','factory:factory'])
        temp=Path(fixture.temp.name)
        index=build(ROOT,temp/'templates')
        contracts=[json.loads((temp/'templates'/Path(r['path']).name).read_bytes()) for r in index['items']]
        for contract in contracts:
            for source in contract['sources']:
                target=fixture.root/source['path'];target.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(ROOT/source['path'],target)
        key=temp/'disposable-judge.pem';initialize_key(key);judge=Signer(key)
        verdict=judge.sign(dict(verdict='equivalent',oracle_status='provisional',run_class='engineering',
            fixture_only=True,meaning='Control-path rehearsal; no candidate comparison or production authority'))
        report=issue(verdict,adequacy,threshold['compared_fields'],judge)
        class_ids=sorted(r['id'] for r in reviews.values() if r.get('class_covered'))
        excluded={r['mutant_id'] for r in adequacy['systematic_mutation']['equivalent_dispositions']}
        individual_ids=sorted(excluded-set(class_ids))
        if not individual_ids:raise ValueError('rehearsal-empty-review-inventory')
        for position,ids in ((1,class_ids),(2,individual_ids)):
            contracts[position]['details'].update(items=ids,packet_sha256=digest(report))
        for position in (3,5):
            contracts[position]['details'].update(evidence_head=head,required_review_ids=individual_ids)
        # Rebinding measured inputs changes unsigned template bodies and hence
        # the packet identity, before any disposable decision is produced.
        bodies=[body_hash(c) for c in contracts];packet=digest(bodies)
        for position,c in enumerate(contracts):
            c['signing_order'].update(packet_sha256=packet,
                predecessor_contract_sha256=bodies[position-1] if position else None)
        backfill=fixture.contract('factory-decision-backfill')
        bp,_,_=fixture.decide(backfill)
        proofs=[]
        for position,c in enumerate(contracts[:5]):
            if position:c=bind_predecessor(c,proofs[-1]);contracts[position]=c
            proof,_,_=fixture.decide(c);proofs.append(proof)
        effective=bind_predecessor(contracts[5],proofs[-1])
        reviews_proof=fixture.service.proof(fixture.token,proofs[2]['decision_sha256'])
        run=int(os.environ['GITHUB_RUN_ID'])
        source_files={p.name:sha256(p.read_bytes()).hexdigest() for p in folder.glob('*.json')}
        values=[('docs/factory/rehearsal-b1.json',summary),
            ('docs/factory/rehearsal-reviews.json',dict(schema='threshold-equivalence-reviews/1',
                program='INTCALC',evidence_head=head,required_ids=individual_ids,claim_scope='twin',proofs=[reviews_proof])),
            ('docs/factory/rehearsal-campaign.json',dict(schema='release-evidence-index/2',head=head,
                conclusion='success',run_id=run,scope='Completed aggregate stages only; not the still-running workflow conclusion',
                sources=[dict(head=head,run_id=run,files=source_files)])),
            ('docs/factory/keep-or-fix-register.json',json.loads((ROOT/'docs/factory/keep-or-fix-register.json').read_bytes()))]
        effective['details']['conditions']=[]
        for condition,(path,value) in zip(CONDITIONS,values):
            target=fixture.root/path
            raw=target.read_bytes() if path.endswith('keep-or-fix-register.json') else (json.dumps(value,sort_keys=True)+'\n').encode()
            if not target.exists():target.write_bytes(raw)
            source=dict(path=path,sha256=sha256(raw).hexdigest(),commit=head)
            # Reuse an already-bound register source instead of duplicating it.
            existing=next((s for s in effective['sources'] if s['path']==path),None)
            if existing:source=deepcopy(existing)
            else:effective['sources'].append(source)
            effective['details']['conditions'].append(dict(condition_sha256=sha256(condition.encode()).hexdigest(),state='met',evidence=source))
        ep,_,_=fixture.decide(effective)
        current=lambda proof:fixture.service.proof(fixture.token,proof['decision_sha256'])
        ep=current(ep)
        authority=FactoryAuthority(fixture.service.public_key,ep['journal']['journal_head_sha256'],current(bp),backfill,evidence_root=fixture.root)
        bundle=dict(threshold=policy,approval=ep,io=[current(proofs[4])],
                    equivalents=[current(proofs[1]),current(proofs[2])],claim_scope='twin')
        result=release(verdict,report,judge.public,bundle,factory_authority=authority)
        from lightyear_factory.release_grade import NAMES
        # This remains an engineering fixture, with no retained release packet or production trust.
        if result['reasons'] != sorted(NAMES):
            raise ValueError('request-06-unexpected-reasons:'+','.join(result['reasons']))
        receipt=dict(schema='intcalc-request06-ci-rehearsal/1',head=head,run_id=run,
            evidence_files=source_files,constant_fields=sorted(adequacy['constant_field_evidence']),
            reasons=result['reasons'],release_grade=result['release_grade'],releasable=False,disposable_ci_signatures_only=True,
            real_requests_signed=False,activation_performed=False,phase2_executed=False,
            authorized_by='Howard',performed_by='Codex CI rehearsal')
        receipt['content_sha256']=digest(receipt)
        output.write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
    finally:fixture.doCleanups()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('aggregate');parser.add_argument('output')
    args=parser.parse_args();rehearse(args.aggregate,args.output)
