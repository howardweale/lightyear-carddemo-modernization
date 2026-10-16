"""Large byte-key browse proof; typed reconstruction remains a separate gate."""
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import time

from .plan import build
from .schema import quote
from .store import Store
from .codec import split_fixed


def generated(template, key, count):
    """Unique display-digit keys, retaining all other public record bytes."""
    width=key['key_length'];offset=key['key_offset']
    if count < 1 or count >= 10**width: raise ValueError('volume-key-capacity')
    for number in range(count):
        value=str(number).zfill(width).encode('cp037')
        yield template[:offset]+value+template[offset+width:]


def boundary_cases(keys):
    """Fixed boundary inventory avoids quadratic enumeration of every start key."""
    ordered=sorted(set(keys));width=len(ordered[0])
    samples=[ordered[i] for i in sorted({0,1,len(ordered)//2,len(ordered)-2,len(ordered)-1}) if 0<=i<len(ordered)]
    starts={b'\0'*width,b'\xff'*width,*samples}
    prefixes={b'',b'\0',b'\xff',*('A0Z9'.encode('cp037')[:n] for n in (1,2,4))}
    prefixes.update(k[:n] for k in samples for n in (1,max(1,width//2),width))
    return [(None,None)]+[(k,None) for k in sorted(starts)]+[(None,k) for k in sorted(prefixes)]+[(k,k[:1]) for k in samples]


def check_browse(store, originals):
    checks=[];primary=store.mapping['keys'][0]
    get=lambda raw,k:raw[k['key_offset']:k['key_offset']+k['key_length']]
    for key in store.mapping['keys']:
        reference=sorted([(get(raw,key),get(raw,primary),i) for i,raw in enumerate(originals,1)])
        for reverse in (False,True):
            ordered=list(reversed(reference)) if reverse else reference
            for start,prefix in boundary_cases([row[0] for row in reference]):
                expected=[i for k,_,i in ordered if (start is None or (k<=start if reverse else k>=start)) and (prefix is None or k.startswith(prefix))]
                begin=time.monotonic();actual=store.browse(key['column'],start=start,prefix=prefix,reverse=reverse)
                fingerprint=lambda ids:sha256(b''.join(i.to_bytes(8,'big') for i in ids)).hexdigest()
                checks.append(dict(index=key['name'],reverse=reverse,start_hex=None if start is None else start.hex(),
                    prefix_hex=None if prefix is None else prefix.hex(),records=len(actual),expected_records=len(expected),
                    expected_sha256=fingerprint(expected),actual_sha256=fingerprint(actual),equal=actual==expected,
                    seconds=time.monotonic()-begin))
    return dict(compared=len(checks),matched=sum(r['equal'] for r in checks),checks=checks)


def load_index(connection, mapping, records):
    columns=['source_ordinal','raw_record']+[k['column'] for k in mapping['keys']]
    connection.execute('CREATE TABLE '+quote(mapping['table'])+' (source_ordinal bigint UNIQUE NOT NULL, raw_record bytea NOT NULL, '+
        ','.join(quote(k['column'])+' bytea NOT NULL'+(' PRIMARY KEY' if k['column']=='ebcdic_key' else '') for k in mapping['keys'])+')')
    with connection.cursor() as cursor:
        with cursor.copy('COPY '+quote(mapping['table'])+' ('+','.join(map(quote,columns))+') FROM STDIN') as stream:
            for i,raw in enumerate(records,1):stream.write_row((i,raw,*[raw[k['key_offset']:k['key_offset']+k['key_length']] for k in mapping['keys']]))
    for k in mapping['keys'][1:]:connection.execute('CREATE INDEX ON '+quote(mapping['table'])+' ('+quote(k['column'])+', ebcdic_key)')
    connection.execute('ANALYZE '+quote(mapping['table']))


def run(connection, root, count):
    plan,entries=build(root);reports=[]
    for item,layout,mapping in entries:
        if item.get('synthetic'):continue
        begin=time.monotonic();template=split_fixed((root/'upstream'/item['data']).read_bytes(),layout.record_length)[0]
        records=list(generated(template,mapping['keys'][0],count))
        load_index(connection,mapping,records)
        load_seconds=time.monotonic()-begin
        store=Store(connection,mapping,layout);gate=check_browse(store,records)
        rows=connection.execute('SELECT source_ordinal,raw_record FROM '+quote(mapping['table'])+' ORDER BY source_ordinal').fetchall()
        exact=len(rows)==count and all(bytes(raw)==records[i-1] for i,raw in rows)
        disk=connection.execute('SELECT pg_total_relation_size(%s)',(mapping['table'],)).fetchone()[0]
        reports.append(dict(table=mapping['table'],records=count,bytes=sum(map(len,records)),relation_bytes=disk,
            load_seconds=load_seconds,wall_seconds=time.monotonic()-begin,raw_round_trip=exact,browse=gate,
            dataset_sha256=sha256(b''.join(records)).hexdigest()))
    # Raw key semantics include non-display bytes which would be invalid in PIC 9.
    # Keep these explicitly separate from the valid-record data set.
    edge=[b'\0'*8,b'\xff'*8]+[s.encode('cp037').ljust(8,b'\x40') for s in ('A0','A00','A09','A1','Z9','0A','9Z',' A','a0')]
    edge_mapping=dict(table='byte_key_edges',keys=[dict(column='ebcdic_key',name='raw-byte-key',key_offset=0,key_length=8)])
    load_index(connection,edge_mapping,edge)
    edge_result=check_browse(Store(connection,edge_mapping,None),edge)
    ok=all(r['raw_round_trip'] and r['browse']['matched']==r['browse']['compared'] for r in reports) and edge_result['matched']==edge_result['compared']
    return dict(schema='carddemo-volume-browse/1',head=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        plan_sha256=plan['content_sha256'],records_per_file=count,files=reports,byte_key_edges=edge_result,
        scope='PostgreSQL raw-record byte-key browse at volume; not typed reconstruction at volume or a z/OS baseline',
        baseline='Independent Python lexicographic sort/filter of generated original key bytes',
        verdict='equivalent' if ok else 'divergent',release_authorized=False)


if __name__=='__main__':
    import psycopg
    p=argparse.ArgumentParser();p.add_argument('--count',type=int,default=100000);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    with psycopg.connect(os.environ['CARDDEMO_DATA_DSN']) as c:
        c.execute('CREATE SCHEMA carddemo_volume');c.execute('SET LOCAL search_path TO carddemo_volume')
        result=run(c,Path('spec/modernization/carddemo-data'),a.count)
        result['content_sha256']=sha256(json.dumps(result,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        (a.out/'volume-receipt.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
        c.rollback()
    raise SystemExit(0 if result['verdict']=='equivalent' else 1)
