"""Bounded public targeted witnesses; not the proposed generic scenario engine."""
from decimal import Decimal
import hashlib
import random
from .records import load_copybook
from .zos_bindings import ROOT, dataset_binding, load_bindings
from carddemo_oracle.records import encode_zoned

SEED='Howard-B1-2026-10-11-200'
PROFILES=('numeric','xref-suffix','timestamp','record-count','status-path','storage-display')


def profile(mutant, argument):
    text=mutant['original']+' '+argument.get('argument','')
    if 'XREF-' in text or mutant.get('source_path')=='CVACT03Y.cpy':kind='xref-suffix'
    elif any(x in text for x in ('DB2-','TIMESTAMP','TRANID-SUFFIX')):kind='timestamp'
    elif any(x in text for x in ('RECORD-COUNT','WS-COUNTERS','END-OF-FILE')):kind='record-count'
    elif any(x in text for x in ('TWO-BYTES','TIMING','IO-STATUS')):kind='storage-display'
    elif any(x in text for x in ('REWRITE','status','abend','PERFORM','VALIDATION')):kind='status-path'
    else:kind='numeric'
    return dict(name=kind,seed=SEED,count=200,mutant_id=mutant['id'],
        argument_sha256=hashlib.sha256(argument.get('argument','').encode()).hexdigest(),
        field_plan={
            'numeric':['amount/balance in cents','rate','credit/debit state','normal and reject paths'],
            'xref-suffix':['customer suffix','account suffix with coordinated account keys'],
            'timestamp':['runtime date/time','processing parameter date','multi-record suffix count'],
            'record-count':['0..199 source records','account transitions'],
            'status-path':['selected declared I/O fault paths','amount','credit/debit state'],
            'storage-display':['selected normal/extended status paths','amount','credit/debit state']
        }[kind],
        limitation='Curated targeted engineering attempts; finite cases do not prove equivalence. Internal storage/ABI semantics remain bound to recorded compiler probes, not varied by fabricated input fields.')


def case(identifier):
    from .scenario_generation import case as curated
    parts=identifier.split(':')
    if len(parts)==4 and parts[0]=='b1-target' and parts[2]=='equivalence-cex':
        from .equivalence_scenarios import case as counterexample
        return counterexample(identifier)
    if len(parts)!=4 or parts[0]!='b1-target' or parts[1] not in ('INTCALC','POSTTRAN') or parts[2] not in PROFILES:
        raise ValueError('target-witness-identifier')
    job,kind=parts[1:3]; index=int(parts[3])
    if not 0<=index<200:raise ValueError('target-witness-bound')
    rng=random.Random(SEED+job+kind+str(index))
    base='intcalc-three-accounts' if job=='INTCALC' else 'posttran-positive'
    if job=='POSTTRAN' and kind=='status-path':
        base=('posttran-positive','posttran-invalid-then-valid','posttran-new-then-existing','posttran-missing-card','posttran-missing-account')[index%5]
    _,meta,images,_=curated(base);images=dict(images);meta=dict(meta)
    changes=[]
    def field(dd,name,value):
        binding=dataset_binding(load_bindings(),job,'STEP15',dd);layout=load_copybook(ROOT/binding['copybook'])
        item=next(f for f in layout.fields if f.path.split('.')[-1]==name)
        if item.digits:
            text=encode_zoned(Decimal(value),item.digits,item.scale) if item.signed else str(int(value)).zfill(item.length)
        else:text=str(value).ljust(item.length)
        raw=text.encode('ascii')
        if len(raw)!=item.length:raise ValueError('target-field-width')
        rows=bytearray(images[dd])
        for start in range(0,len(rows),layout.record_length+1):rows[start+item.offset:start+item.offset+item.length]=raw
        images[dd]=bytes(rows);changes.append(dict(dataset=dd,field=name,value=str(value)))
    if kind=='xref-suffix':
        if job=='POSTTRAN':
            # Keep the selected transaction's foreign-key chain coherent while
            # changing the exact receiving account suffix claimed irrelevant.
            from .posttran_invariants import records
            card=records(images,'DALYTRAN')[0]['DALYTRAN-CARD-NUM']
            xrefs=records(images,'XREFFILE'); xi=next(i for i,r in enumerate(xrefs) if r['XREF-CARD-NUM']==card)
            aid=xrefs[xi]['XREF-ACCT-ID']; ai=next(i for i,r in enumerate(records(images,'ACCTFILE')) if r['ACCT-ID']==aid)
            for dd,ordinal in [('XREFFILE',xi),('ACCTFILE',ai)]:
                size=load_copybook(ROOT/dataset_binding(load_bindings(),job,'STEP15',dd)['copybook']).record_length+1
                images[dd]=images[dd][ordinal*size:(ordinal+1)*size]
            images['TCATBALF']=b''
            field('XREFFILE','XREF-ACCT-ID',100000+index);field('ACCTFILE','ACCT-ID',100000+index)
        field('XREFFILE','XREF-CUST-ID',rng.randint(0,999999999))
        # The scale mutation reads the first unused suffix byte as fractional
        # storage; vary it over printable bytes without changing an indexed key.
        xref=bytearray(images['XREFFILE'])
        for start in range(0,len(xref),51):xref[start+36]=33+index%94
        images['XREFFILE']=bytes(xref);changes.append(dict(field='XREF-unused-filler-first-byte',value=33+index%94))
        # INTCALC alternate account lookup must remain coherent with balances.
        if job=='INTCALC':
            for dd,name in [('XREFFILE','XREF-ACCT-ID'),('ACCTFILE','ACCT-ID'),('TCATBALF','TRANCAT-ACCT-ID')]:
                # Keep a single account so coordinated keys stay unique.
                size=load_copybook(ROOT/dataset_binding(load_bindings(),job,'STEP15',dd)['copybook']).record_length+1
                images[dd]=images[dd][:size];field(dd,name,100000+index)
    elif kind=='timestamp':
        day=1+index%28;hour=index%24;minute=index%60
        meta['candidate_timestamp']=f'2022-06-{day:02d}-{hour:02d}.{minute:02d}.00.000000'
        if job=='INTCALC':meta['processing_date']=f'202206{day:02d}{hour:02d}'
        changes.append(dict(field='runtime-clock',value=meta['candidate_timestamp']))
        if job=='INTCALC':
            # Exercise more than the first suffix value, retaining valid category
            # and disclosure keys for each account transition.
            size=load_copybook(ROOT/dataset_binding(load_bindings(),job,'STEP15','TCATBALF')['copybook']).record_length+1
            images['TCATBALF']=images['TCATBALF'][:size*(1+index%3)]
            changes.append(dict(field='TCATBALF-record-count',value=1+index%3))
    elif kind=='record-count':
        dd='TCATBALF' if job=='INTCALC' else 'DALYTRAN';size=load_copybook(ROOT/dataset_binding(load_bindings(),job,'STEP15',dd)['copybook']).record_length+1
        first=images[dd][:size];rows=[]
        for ordinal in range(index):
            row=bytearray(first)
            # Distinct numeric category/transaction keys avoid adapter admission failures.
            name='TRANCAT-CD' if job=='INTCALC' else 'DALYTRAN-ID'
            item=next(f for f in load_copybook(ROOT/dataset_binding(load_bindings(),job,'STEP15',dd)['copybook']).fields if f.path.split('.')[-1]==name)
            row[item.offset:item.offset+item.length]=str(ordinal+1).zfill(item.length).encode();rows.append(bytes(row))
        images[dd]=b''.join(rows);changes.append(dict(field=dd+'-record-count',value=len(rows)))
    else:
        cents=rng.randint(-99999,99999);amount=str(Decimal(cents)/100)
        if job=='INTCALC':field('TCATBALF','TRAN-CAT-BAL',amount);field('DISCGRP','DIS-INT-RATE',str(Decimal(rng.randint(0,9999))/100))
        else:
            field('DALYTRAN','DALYTRAN-AMT',amount)
            field('ACCTFILE','ACCT-CURR-CYC-CREDIT',str(Decimal(rng.randint(0,150000))/100))
            field('ACCTFILE','ACCT-CURR-CYC-DEBIT',str(Decimal(rng.randint(-50000,50000))/100))
    meta['public_input_variant']=identifier
    return job,meta,images,dict(id=identifier,generator_class='curated-finite-witness',targeted=True,seed=SEED,index=index,profile=kind,changes=changes,
        input_sha256={dd:hashlib.sha256(raw).hexdigest() for dd,raw in images.items()})
