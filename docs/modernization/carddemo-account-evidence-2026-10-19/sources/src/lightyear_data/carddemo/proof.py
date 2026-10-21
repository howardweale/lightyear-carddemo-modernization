"""Compare PostgreSQL readback to public bytes and independent byte-order references."""
from collections import defaultdict
from decimal import Decimal
from hashlib import sha256
import json

from .codec import project, encode_field, split_fixed
from .schema import ddl, quote
from .store import Store


def gate(compared, matched, **extra):
    return dict(verdict='indeterminate' if not compared else 'equivalent' if matched==compared else 'divergent',
                compared=compared, matched=matched, **extra)


def browse_gate(store, originals, loaded):
    comparisons=[]
    for key in store.mapping['keys']:
        def key_bytes(i):return originals[i-1][key['key_offset']:key['key_offset']+key['key_length']]
        primary=store.mapping['keys'][0]
        def tie(i):return originals[i-1][primary['key_offset']:primary['key_offset']+primary['key_length']]
        ordered=sorted(loaded,key=lambda i:(key_bytes(i),tie(i)))
        starts={b'\x00'*key['key_length'],b'\xff'*key['key_length'],*(key_bytes(i) for i in loaded)}
        prefixes={b'',*(key_bytes(i)[:n] for i in loaded for n in (1,max(1,key['key_length']//2),key['key_length']))}
        for reverse in (False,True):
            expected=list(reversed(ordered)) if reverse else ordered
            cases=[(None,None)] + [(s,None) for s in sorted(starts)] + [(None,p) for p in sorted(prefixes)]
            for start,prefix in cases:
                wanted=[i for i in expected if (start is None or (key_bytes(i)<=start if reverse else key_bytes(i)>=start))
                        and (prefix is None or (key_bytes(i)<=prefix.ljust(key['key_length'],b'\xff') if reverse else key_bytes(i)>=prefix))]
                actual=store.browse(key['column'],start=start,prefix=prefix,reverse=reverse)
                comparisons.append(dict(index=key['name'],reverse=reverse,start_hex=start.hex() if start is not None else None,
                    prefix_hex=prefix.hex() if prefix is not None else None,expected=wanted,actual=actual,equal=wanted==actual))
    return gate(len(comparisons),sum(c['equal'] for c in comparisons),cases=comparisons,
                baseline='independent sort/filter of original EBCDIC key slices')


def reconcile(store, originals):
    rows=store.rows(); ids=[r['source_ordinal'] for r in rows]
    roundtrip=[]; totals=defaultdict(Decimal)
    for row in rows:
        original=originals[row['source_ordinal']-1]
        source_projection=project(store.layout,store.mapping,original)
        try:
            if row['encoding_meta'] != source_projection['metadata'] or row['source_sha256'] != source_projection['source_sha256']:
                raise ValueError('source-bound representation metadata changed')
            actual=store.bytes(row);equal=actual==original;reason=None
        except (ValueError,KeyError,UnicodeError) as error:actual=b'';equal=False;reason=str(error)
        roundtrip.append(dict(source_ordinal=row['source_ordinal'],equal=equal,reason=reason,
                              source_sha256=sha256(original).hexdigest(),reencoded_sha256=sha256(actual).hexdigest()))
        values=source_projection['values']
        for f in store.mapping['fields']:
            if f['digits'] and not f['filler'] and f['path'] in values:
                totals[f['table']+'.'+f['column']]+=values[f['path']]
    actual_totals=store.totals()
    with store.connection.cursor() as cursor:
        cursor.execute('SELECT source_ordinal, raw_record, source_sha256, reason FROM '+quote('quarantine_'+store.table)+' ORDER BY source_ordinal')
        quarantined=cursor.fetchall()
    qids=[r[0] for r in quarantined]
    preserved=all(1<=i<=len(originals) and bytes(raw)==originals[i-1] and digest==sha256(bytes(raw)).hexdigest() for i,raw,digest,_ in quarantined)
    accounted=sorted(ids+qids)==list(range(1,len(originals)+1)) and len(set(ids+qids))==len(originals)
    total_rows=[dict(field=k,source=str(totals.get(k,Decimal(0))),postgres=str(v),equal=totals.get(k,Decimal(0))==v) for k,v in actual_totals.items()]
    return dict(table=store.table,records=len(originals),loaded=len(rows),quarantined=len(quarantined),
        quarantine=[dict(source_ordinal=i,sha256=digest,reason=reason) for i,_,digest,reason in quarantined],
        round_trip=gate(len(rows),sum(r['equal'] for r in roundtrip),records=roundtrip),
        reconciliation=gate(2+len(total_rows),int(accounted)+int(preserved)+sum(r['equal'] for r in total_rows),
            record_accounting=accounted,quarantine_bytes_preserved=preserved,control_totals=total_rows,
            control_total_scope='accepted records; rejected records retained individually in quarantine'),
        browse_order=browse_gate(store,originals,ids) if store.mapping['keys'] and not store.mapping.get('segment') else dict(verdict='indeterminate',reason='not a VSAM key browse; segment traversal or RBA/slot ordering is separate'))


def synthetic_segment(layout, mapping, seed):
    """Generated fixture only, not presented as an IMS capture or public unload."""
    raw=bytearray(b'\x40'*layout.record_length)
    for f in mapping['fields']:
        if f['filler']:continue
        value=Decimal(seed % (10**min(f['digits'],3))) / (10**f['scale']) if f['digits'] else ('A'+str(seed)).ljust(f['length'])[:f['length']]
        encoded=encode_field(f,value,{},'cp037');raw[f['offset']:f['offset']+f['length']]=encoded
    return bytes(raw)


def ims_fixture(connection, entries):
    ims=[(item,layout,m) for item,layout,m in entries if m.get('segment')]
    if len(ims)!=2:raise ValueError('bounded IMS proof requires one root and one child type')
    _,rl,rm=next(x for x in ims if x[2]['segment']['parent'] is None)
    _,cl,cm=next(x for x in ims if x[2]['segment']['parent'] is not None)
    if cm['segment']['parent'].lower()!=rm['table']:raise ValueError('unsupported IMS hierarchy')
    root=Store(connection,rm,rl);child=Store(connection,cm,cl)
    roots=[synthetic_segment(rl,rm,seed) for seed in (2,1)]
    details=[];parents={}
    for i,raw in enumerate(roots,1):
        loaded=root.load_one(raw,i,twin_seq=i)
        if loaded['status']!='loaded':raise ValueError('synthetic root rejected')
        parent=loaded['path_key'];parents[parent]=raw
        for seed in (3,1):
            r=synthetic_segment(cl,cm,seed);details.append(r)
            if child.load_one(r,len(details),parent_path=parent,twin_seq=seed)['status']!='loaded':raise ValueError('synthetic child rejected')
    # Reference walks a Python hierarchy built from original segment bytes.
    rk=rm['keys'][0];ck=cm['keys'][0]
    rootkey=lambda raw:raw[rk['key_offset']:rk['key_offset']+rk['key_length']]
    childkey=lambda raw:raw[ck['key_offset']:ck['key_offset']+ck['key_length']]
    reference=[]
    for raw in sorted(roots,key=rootkey):
        reference.append((rm['table'],raw.hex()))
        for r in sorted([synthetic_segment(cl,cm,seed) for seed in (3,1)],key=childkey):reference.append((cm['table'],r.hex()))
    # Candidate order comes from database bytea indexes, then typed row reconstruction.
    from psycopg.rows import dict_row
    observed=[]
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute('SELECT * FROM '+quote(rm['table'])+' ORDER BY ebcdic_key')
        rootrows=cursor.fetchall()
        for row in rootrows:
            observed.append((rm['table'],root.bytes(row).hex()))
            cursor.execute('SELECT * FROM '+quote(cm['table'])+' WHERE parent_path_key=%s ORDER BY ebcdic_key',(row['path_key'],))
            for detail in cursor.fetchall():observed.append((cm['table'],child.bytes(detail).hex()))
    return dict(baseline='generated two-level byte-stream reference; not the existing 40-case DL/I corpus',
        segment_reports=[reconcile(root,roots),reconcile(child,details)],
        traversal=gate(1,int(reference==observed),segments_compared=len(reference),
            source_stream_sha256=sha256(json.dumps(reference).encode()).hexdigest(),
            postgres_stream_sha256=sha256(json.dumps(observed).encode()).hexdigest()),
        public_unload=dict(verdict='indeterminate',reason='utility unload framing has not been verified'),
        dli_replay=dict(verdict='indeterminate',compared=0,reason='stateful DL/I compatibility and 40-case replay are outside this data-move proof'))


def run(connection, root, plan, entries):
    reports=[]
    for _,_,m in entries:connection.execute(ddl(m))
    for item,layout,m in entries:
        if item.get('synthetic'):continue
        raw=(root/'upstream'/item['data']).read_bytes()
        records=split_fixed(raw,layout.record_length)
        store=Store(connection,m,layout)
        for i,record in enumerate(records,1):store.load_one(record,i)
        reports.append(reconcile(store,records))
    ims=ims_fixture(connection,entries)
    failures=[{'table':r['table'],'gate':k,'verdict':r[k]['verdict']} for r in reports for k in ('round_trip','reconciliation','browse_order') if r[k]['verdict']!='equivalent']
    quarantine=sum(r['quarantined'] for r in reports)
    receipt=dict(schema='carddemo-data-proof/1',claim_scope='public-source-and-generated-twin',
        plan_sha256=plan['content_sha256'],upstream_commit=plan['upstream']['commit'],vsam=reports,ims=ims,
        verdict='divergent' if any(f['verdict']=='divergent' for f in failures) else 'indeterminate',
        failures=failures,quarantined=quarantine,quarantine_approved=False,
        blockers=plan['unsupported']+[{'reason':'No z/OS capture or CICS baseline; no signed release authorization'}],
        screen_gates=dict(verdict='indeterminate',sessions_compared=0,mutation_catch_rate=None,reason='data component only; screens not implemented'),
        quirks=['Preserve source typo ACCT-EXPIRAION-DATE.',
                'CBPAUP0C duplicates the approved-count deletion test; the data move does not change or certify that program.',
                'CARDDATA also has a nonunique account alternate index.',
                'Numeric signs and FILLER must be retained for byte-exact reconstruction.'],
        signed=False,release_authorized=False)
    receipt['content_sha256']=sha256(json.dumps(receipt,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    return receipt
