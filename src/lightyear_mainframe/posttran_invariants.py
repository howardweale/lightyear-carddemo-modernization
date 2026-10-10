"""POSTTRAN conservation checks, not a Python output oracle. Public fixed images only."""
from collections import Counter
from datetime import date
from decimal import Decimal
import json
from pathlib import Path
import re
from .records import load_copybook, from_ascii_fixed
from .zos_bindings import ROOT, load_bindings, dataset_binding


def records(images, dd):
    b=dataset_binding(load_bindings(),'POSTTRAN','STEP15',dd)
    layout=load_copybook(ROOT/b['copybook'])
    return [{f['path'].split('.')[-1]: f['value'] for f in r['fields'] if not f['filler']}
            for r in from_ascii_fixed(layout,images[dd])]


def require_collation_independent(images):
    # The sole relational PIC X comparison is ISO expiry >= origin-date at line414.
    # Fixed separators and decimal-only positions have the same order in ASCII/cp037.
    for r in records(images,'ACCTFILE'):
        value=r['ACCT-EXPIRAION-DATE']
        if not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}',value):
            raise ValueError('POSTTRAN collation-sensitive expiry: stop')
        date.fromisoformat(value)
    for r in records(images,'DALYTRAN'):
        value=r['DALYTRAN-ORIG-TS'][:10]
        if not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}',value):
            raise ValueError('POSTTRAN collation-sensitive origin date: stop')
        date.fromisoformat(value)
    # Indexed bridge iteration/key order is not made EBCDIC by program collation.
    # Current acceptance is restricted to decimal-only physical keys.
    from .legacy_twin import FILES,unframe
    for dd,(length,key) in FILES['POSTTRAN'].items():
        if key:
            raw=unframe(images[dd],length)
            keys=[raw[i:i+key] for i in range(0,len(raw),length)]
            if len(keys)!=len(set(keys)):
                raise ValueError('POSTTRAN duplicate indexed input key: stop')
            if any(not raw[i:i+key].isdigit() for i in range(0,len(raw),length)):
                raise ValueError('POSTTRAN collation-sensitive indexed key: stop')
    return {'status':'restricted-input-path-proved-order-equivalent','zos_confirmation':False}


def check(before,after,*,timestamp):
    require_collation_independent(before)
    daily=records(before,'DALYTRAN'); posted=records(after,'TRANFILE'); rejected=records(after,'DALYREJS')
    accounts={int(r['ACCT-ID']):dict(r) for r in records(before,'ACCTFILE')}
    xrefs={r['XREF-CARD-NUM']:int(r['XREF-ACCT-ID']) for r in records(before,'XREFFILE')}
    cats={(int(r['TRANCAT-ACCT-ID']),r['TRANCAT-TYPE-CD'],int(r['TRANCAT-CD'])):Decimal(r['TRAN-CAT-BAL']) for r in records(before,'TCATBALF')}
    problems=[]
    def require(ok,code):
        if not ok: problems.append(code)
    source_ids=Counter(r['DALYTRAN-ID'] for r in daily)
    posted_ids=Counter(r['TRAN-ID'] for r in posted)
    rejected_ids=Counter(r['DALYTRAN-ID'] for r in rejected)
    require(len(posted)+len(rejected)==len(daily),'record-count-conservation')
    require(source_ids==posted_ids+rejected_ids,'record-id-conservation')
    require(all(v==1 for v in source_ids.values()),'ambiguous-duplicate-input-id')
    require(all(v==1 for v in posted_ids.values()),'duplicate-posted-id')
    pmap={r['TRAN-ID']:r for r in posted}; rmap={r['DALYTRAN-ID']:r for r in rejected}
    for r in daily:
        key=r['DALYTRAN-ID']; amount=Decimal(r['DALYTRAN-AMT'])
        aid=xrefs.get(r['DALYTRAN-CARD-NUM']); a=accounts.get(aid)
        reason=100 if aid is None else 101 if a is None else 0
        if a is not None:
            if Decimal(a['ACCT-CURR-CYC-CREDIT'])-Decimal(a['ACCT-CURR-CYC-DEBIT'])+amount>Decimal(a['ACCT-CREDIT-LIMIT']): reason=102
            if a['ACCT-EXPIRAION-DATE']<r['DALYTRAN-ORIG-TS'][:10]: reason=103
        if key in rmap:
            rejected_row=rmap[key]
            require(int(rejected_row['WS-VALIDATION-FAIL-REASON'])==reason and reason in (100,101,102,103),'rejection-condition:'+key)
            require(all(rejected_row.get(k)==v for k,v in r.items()),'rejected-input-changed:'+key)
        elif key in pmap:
            require(reason==0,'invalid-record-posted:'+key)
            transaction=pmap[key]
            require(all(transaction.get(k.replace('DALYTRAN-','TRAN-'))==v for k,v in r.items() if k!='DALYTRAN-PROC-TS'),'posted-data-changed:'+key)
            require(transaction['TRAN-PROC-TS']==timestamp,'processing-clock:'+key)
            if a is None: continue
            a['ACCT-CURR-BAL']=str(Decimal(a['ACCT-CURR-BAL'])+amount)
            field='ACCT-CURR-CYC-CREDIT' if amount>=0 else 'ACCT-CURR-CYC-DEBIT'
            a[field]=str(Decimal(a[field])+amount)
            cat=(aid,r['DALYTRAN-TYPE-CD'],int(r['DALYTRAN-CAT-CD']))
            cats[cat]=cats.get(cat,Decimal(0))+amount
    actual_accounts={int(r['ACCT-ID']):r for r in records(after,'ACCTFILE')}
    require(len(actual_accounts)==len(records(after,'ACCTFILE')),'duplicate-account-output')
    require(accounts.keys()==actual_accounts.keys(),'account-id-set')
    for aid,a in accounts.items():
        actual=actual_accounts.get(aid,{})
        for field in ('ACCT-CURR-BAL','ACCT-CURR-CYC-CREDIT','ACCT-CURR-CYC-DEBIT'):
            require(field in actual and Decimal(actual[field])==Decimal(a[field]),f'account-conservation:{aid}:{field}')
    actual_cats={(int(r['TRANCAT-ACCT-ID']),r['TRANCAT-TYPE-CD'],int(r['TRANCAT-CD'])):Decimal(r['TRAN-CAT-BAL']) for r in records(after,'TCATBALF')}
    require(len(actual_cats)==len(records(after,'TCATBALF')),'duplicate-category-output')
    require(cats==actual_cats,'category-conservation')
    return dict(schema='posttran-independent-invariants/1',passed=not problems,failures=problems,
                inputs=len(daily),posted=len(posted),rejected=len(rejected),oracle_class='executable-twin',
                oracle_status='provisional',zos_confirmation=False,releasable=False,
                repeatability='requires-separate-second-run',human_review='pending',java_second_opinion='unavailable')


def review_sheet(before,after):
    daily=records(before,'DALYTRAN'); posted=records(after,'TRANFILE'); rejected=records(after,'DALYREJS')
    chosen={}
    for r in sorted(rejected,key=lambda r:r['DALYTRAN-ID']):
        chosen.setdefault('reason-'+str(r['WS-VALIDATION-FAIL-REASON']),r['DALYTRAN-ID'])
    ordered=sorted(posted,key=lambda r:(Decimal(r['TRAN-AMT']),r['TRAN-ID']))
    for label,r in zip(('minimum-posted','maximum-posted'),([ordered[0],ordered[-1]] if ordered else [])):
        chosen[label]=r['TRAN-ID']
    for r in sorted(daily,key=lambda r:r['DALYTRAN-ID']):
        if len(set(chosen.values()))>=10: break
        chosen.setdefault('sample-'+r['DALYTRAN-ID'],r['DALYTRAN-ID'])
    p={r['TRAN-ID']:r for r in posted}; rej={r['DALYTRAN-ID']:r for r in rejected}; inputs={r['DALYTRAN-ID']:r for r in daily}
    return {'schema':'posttran-human-review-sheet/1','review_class':'operator-review-not-independent-attestation',
            'signature':None,'reviewer':None,'status':'awaiting-human-review','records':[
                {'id':key,'input':inputs[key],'twin_output':p.get(key,rej.get(key)),
                 'source':'spec/mainframe/public-source/CBTRN02C.cbl:379-420,423-446,545-561',
                 'expected_result':'Reviewer must check rejection priority, amount conservation and identifiers against source.',
                 'reviewer_decision':None} for key in sorted(set(chosen.values()))]}


def main():
    import argparse
    p=argparse.ArgumentParser();p.add_argument('run',type=Path);p.add_argument('--timestamp',required=True)
    a=p.parse_args()
    from .legacy_twin import FILES,write_json
    before={dd:(a.run/'before'/dd).read_bytes() for dd in FILES['POSTTRAN']}
    # Shared candidate integration expects newline-framed images, same as twin after/.
    after={dd:(a.run/'after'/dd).read_bytes() for dd in FILES['POSTTRAN']}
    result=check(before,after,timestamp=a.timestamp)
    write_json(a.run/'posttran-invariants.json',result)
    if not result['passed']: raise SystemExit(1)

if __name__=='__main__': main()
