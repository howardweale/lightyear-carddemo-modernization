"""Deterministic public generators, finite-domain witnesses and real COBOL mutants."""
from dataclasses import replace
from decimal import Decimal as D
import itertools
from .legacy_twin import public_inputs, ROOT, sha
from .records import load_copybook
from .zos_bindings import load_bindings, dataset_binding
from carddemo_oracle.records import Account, CategoryBalance, Disclosure, CardXref, encode_zoned

SEED='public-scenario-engine-v1'


def boundaries(field):
    if not field.digits:
        return [{'kind':'spaces','value_hex':(' '*field.length).encode().hex()},
                {'kind':'low-values','value_hex':bytes(field.length).hex()}]
    unit=D(1).scaleb(-field.scale); maximum=(D(10)**field.digits-1)*unit
    minimum=-maximum if field.signed else D(0)
    values={minimum,maximum,D(0),unit}
    if field.signed:values.add(-unit)
    return [dict(kind='representable-boundary',value=str(v),picture=field.picture,
                 usage=field.usage,scale=field.scale) for v in sorted(values)]


def solve(domains,predicate):
    """Exhaustive deterministic finite-domain solver; UNSAT is domain-local only."""
    names=sorted(domains)
    count=1
    for n in names:count*=len(domains[n])
    if count>100000:raise ValueError('solver-domain-bound')
    for values in itertools.product(*(sorted(domains[n]) for n in names)):
        witness=dict(zip(names,values))
        if predicate(witness):return dict(status='sat',witness=witness,domain_size=count)
    return dict(status='not-solved',reason='no witness in finite declared domain; not an unreachability proof',domain_size=count)


def manifest():
    result=[]
    def add(job,name,generator,gap,**parameters):
        result.append(dict(id=job.lower()+'-'+name,job=job,generator=generator,target_gap=gap,
                           seed=SEED,parameters=parameters,run_class='engineering',data_class='public-generated'))
    binding=dataset_binding(load_bindings(),'INTCALC','STEP15','TCATBALF')
    layout=load_copybook(ROOT/binding['copybook'])
    field=next(f for f in layout.fields if f.path.endswith('.TRAN-CAT-BAL'))
    for i,row in enumerate(boundaries(field)):
        add('INTCALC','pic-'+str(i),'copybook-pic-boundary','monthly-interest scale/truncation',balance=row['value'],rate='15.00',pic=row)
    # The half-cent boundary for rate 15% is balance .40; adjacent cents straddle it.
    for amount in ('0.39','0.40','0.41','0.79','0.80','0.81','-0.39','-0.40','-0.41'):
        add('INTCALC','round-'+amount.replace('-','n').replace('.','_'),'rounding-boundary','CBACT04C:464 truncation versus ROUNDED',balance=amount,rate='15.00')
    for name in ('empty','two-categories','two-accounts','missing-disclosure','missing-account','missing-xref','duplicate-category'):
        add('INTCALC',name,'cross-record','account/category/final/empty/duplicate boundaries',variant=name,balance='10.01',rate='15.00')
    for truth in (False,True):
        witness=solve({'rate':[D('-.01'),D(0),D('.01'),D('15')]},lambda x:(x['rate']!=0)==truth)
        add('INTCALC','solver-rate-'+str(truth).lower(),'decision-directed-finite-solver','CBACT04C:214 '+str(truth),rate=str(witness['witness']['rate']),balance='10.01',solver={**witness,'witness':{'rate':str(witness['witness']['rate'])}})
    for name in ('zero','positive','negative','credit-equal','credit-above','expiry-equal','expiry-before','missing-card','missing-account','empty','duplicate-id','new-category'):
        add('POSTTRAN',name,'boundary-or-cross-record','CBTRN02C validation/posting/EOF',variant=name)
    for truth in (False,True):
        witness=solve({'amount':[D('999.99'),D('1000'),D('1000.01')]},lambda x:(D('1000')>=x['amount'])==truth)
        add('POSTTRAN','solver-credit-'+str(truth).lower(),'decision-directed-finite-solver',
            'IF ACCT-CREDIT-LIMIT >= WS-TEMP-BAL '+str(truth),variant='solver-credit',amount=str(witness['witness']['amount']),
            solver={**witness,'witness':{'amount':str(witness['witness']['amount'])}})
    for spec in result:
        program='CBACT04C' if spec['job']=='INTCALC' else 'CBTRN02C'
        source=ROOT/f'spec/mainframe/public-source/{program}.cbl'
        spec['source_sha256']=sha(source.read_bytes())
        if spec['generator']=='decision-directed-finite-solver':
            condition='IF DIS-INT-RATE NOT = 0' if spec['job']=='INTCALC' else 'IF ACCT-CREDIT-LIMIT >= WS-TEMP-BAL'
            spec['condition']=condition
            spec['condition_line']=next(i for i,s in enumerate(source.read_text().splitlines(),1) if condition in s)
    return result


def case(identifier):
    spec=next((s for s in manifest() if s['id']==identifier),None)
    if spec is None:raise ValueError('unknown-generated-scenario')
    job=spec['job']; p=spec['parameters']
    _,meta,images,_=public_inputs('intcalc-discriminating' if job=='INTCALC' else 'posttran-public')
    meta=dict(meta,public_input_variant=identifier)
    def render(rows):return b''.join((r.render()+'\n').encode('ascii') for r in rows)
    if job=='INTCALC':
        accounts=[Account.parse(s) for s in images['ACCTFILE'].decode().splitlines()][:2]
        accounts=[replace(a,current_balance=D('10'),group_id='DIRECT    ') for a in accounts]
        xrefs=[CardXref.parse(s) for s in images['XREFFILE'].decode().splitlines()][:2]
        balances=[CategoryBalance(accounts[0].account_id,'01','0001',D(p['balance']))]
        disclosures=[Disclosure('DIRECT    ','01','0001',D(p['rate']))]
        variant=p.get('variant')
        if variant=='empty':balances=[]
        if variant=='two-categories':
            balances.append(replace(balances[0],category_code='0002'))
            disclosures.append(replace(disclosures[0],category_code='0002'))
        if variant=='two-accounts':balances.append(replace(balances[0],account_id=accounts[1].account_id))
        if variant=='missing-disclosure':disclosures=[]
        if variant=='missing-account':accounts=[]
        if variant=='missing-xref':xrefs=[]
        if variant=='duplicate-category':balances*=2
        images=dict(ACCTFILE=render(accounts),XREFFILE=render(xrefs),TCATBALF=render(balances),DISCGRP=render(disclosures),TRANSACT=b'')
    else:
        # Keep one original public transaction and its referenced public input files.
        images={**images,'DALYTRAN':images['DALYTRAN'][:351]}
        def setfield(dd,name,value):
            b=dataset_binding(load_bindings(),job,'STEP15',dd);lay=load_copybook(ROOT/b['copybook'])
            f=next(f for f in lay.fields if f.path.split('.')[-1]==name)
            encoded=(encode_zoned(D(value),f.digits,f.scale) if f.signed else str(value).ljust(f.length)).encode('ascii')
            if len(encoded)!=f.length:raise ValueError('generated-field-width')
            raw=bytearray(images[dd])
            for i in range(0,len(raw),lay.record_length+1):raw[i+f.offset:i+f.offset+f.length]=encoded
            images[dd]=bytes(raw)
        variant=p['variant']
        setfield('ACCTFILE','ACCT-CURR-CYC-CREDIT','0');setfield('ACCTFILE','ACCT-CURR-CYC-DEBIT','0')
        setfield('ACCTFILE','ACCT-CREDIT-LIMIT','1000');setfield('ACCTFILE','ACCT-EXPIRAION-DATE','2030-01-01')
        amount=p.get('amount',{'zero':'0','negative':'-0.01','credit-equal':'1000','credit-above':'1000.01'}.get(variant,'0.01'))
        setfield('DALYTRAN','DALYTRAN-AMT',amount)
        if variant.startswith('expiry-'):setfield('ACCTFILE','ACCT-EXPIRAION-DATE','2022-06-10' if variant=='expiry-equal' else '1900-01-01')
        if variant=='missing-card':setfield('DALYTRAN','DALYTRAN-CARD-NUM','9999999999999999')
        if variant=='missing-account':images['ACCTFILE']=b''
        if variant=='empty':images['DALYTRAN']=b''
        if variant=='duplicate-id':images['DALYTRAN']*=2
        if variant=='new-category':images['TCATBALF']=b''
    return job,meta,images,{**spec,'input_sha256':{dd:sha(raw) for dd,raw in images.items()}}


MUTANTS={
 'intcalc-rounded':('INTCALC','COMPUTE WS-MONTHLY-INT','COMPUTE WS-MONTHLY-INT ROUNDED'),
 'intcalc-scale':('INTCALC','WS-MONTHLY-INT            PIC S9(09)V99.','WS-MONTHLY-INT            PIC S9(09)V9.'),
 'intcalc-divisor':('INTCALC','/ 1200','/ 120'),
 'intcalc-relational':('INTCALC','IF DIS-INT-RATE NOT = 0','IF DIS-INT-RATE > 0'),
 'intcalc-drop-write':('INTCALC','PERFORM 1300-B-WRITE-TX.','CONTINUE.'),
 'posttran-credit':('POSTTRAN','IF ACCT-CREDIT-LIMIT >= WS-TEMP-BAL','IF ACCT-CREDIT-LIMIT > WS-TEMP-BAL'),
 'posttran-expiry':('POSTTRAN','IF ACCT-EXPIRAION-DATE >= DALYTRAN-ORIG-TS','IF ACCT-EXPIRAION-DATE > DALYTRAN-ORIG-TS'),
 'posttran-drop-update':('POSTTRAN','PERFORM 2800-UPDATE-ACCOUNT-REC','CONTINUE'),
}


def mutate(text,job,identifier):
    if identifier not in MUTANTS:raise ValueError('unknown-legacy-mutant')
    scope,old,new=MUTANTS[identifier]
    if scope!=job:return text
    if text.count(old)!=1:raise ValueError('mutant-source-anchor')
    return text.replace(old,new)
