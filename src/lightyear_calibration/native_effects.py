"""Observe native row multisets and structural changes without predicting effects."""
from __future__ import annotations
from collections import Counter
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import re

from .contracts import canonical, digest, require, seal, verify
from .native_catalog import json_value, query


def row_delta(before, after):
    """Keep duplicate multiplicities and every raw value, including runtime clocks."""
    left, right = Counter(before), Counter(after)
    return {'removed':dict(sorted((left-right).items())), 'added':dict(sorted((right-left).items()))}


def capture_rows(connection, lane, output):
    """Complete ordinary base-table row capture; no views and no sampling."""
    require(lane in ('oracle', 'postgresql'), 'Unknown native lane')
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    if lane=='postgresql':
        # The real seed contains a BC timestamp. Python datetime cannot represent
        # it; retain the server's literal instead of losing the row or changing
        # the database to fit the client library.
        import psycopg
        from psycopg.types.datetime import TimestampLoader, TimestamptzLoader, DateLoader
        for oid,base in [(1114,TimestampLoader),(1184,TimestamptzLoader),(1082,DateLoader)]:
            def load(self,data,_base=base,_oid=oid):
                try:return _base.load(self,data)
                except psycopg.DataError:return {'native_datetime_literal':bytes(data).decode('ascii'),'postgresql_type_oid':_oid}
            connection.adapters.register_loader(oid,type('RetainingDateLoader',(base,),{'load':load}))
    tables = query(connection, "SELECT table_name FROM user_tables WHERE nested='NO' AND secondary='N'" if lane=='oracle' else
                   "SELECT table_name FROM information_schema.tables WHERE table_schema='adempiere' AND table_type='BASE TABLE'")
    rows = {}
    for item in tables:
        table=item['table_name']
        require(re.fullmatch(r'[A-Z][A-Z0-9_$#]*' if lane=='oracle' else r'[a-z_][a-z_0-9]*',table), 'Unsupported native identifier')
        key=table.lower()
        filename=hashlib.sha256(table.encode()).hexdigest()+'.rows.jsonl.gz'
        counts=Counter();total=0
        with connection.cursor() as cursor, gzip.open(output/filename,'wb') as file:
            cursor.execute('SELECT * FROM '+('"'+table+'"' if lane=='oracle' else 'adempiere."'+table+'"'))
            names=[c[0].lower() for c in cursor.description]
            require(len(names)==len(set(names)), 'Case-folded column collision')
            while batch:=cursor.fetchmany(1000):
                for row in batch:
                    record=dict(zip(names,map(json_value,row)))
                    payload=canonical(record);counts[hashlib.sha256(payload).hexdigest()]+=1
                    file.write(payload+b'\n');total+=1
                    require(total<=2000000, 'Table capture exceeds row bound')
        rows[key]={'rows':total,'row_multiset':dict(sorted(counts.items())), 'raw_file':filename,
                   'raw_file_sha256':hashlib.sha256((output/filename).read_bytes()).hexdigest()}
    structure_queries = ({
        'columns':"SELECT table_name,column_name,data_type,data_length,data_precision,data_scale,nullable,data_default,char_used,char_length,virtual_column,identity_column FROM user_tab_cols WHERE hidden_column='NO'",
        'constraints':"SELECT table_name,constraint_name,constraint_type,search_condition,r_constraint_name,delete_rule,status,deferrable,deferred,validated FROM user_constraints",
        'indexes':"SELECT index_name,table_name,index_type,uniqueness,status FROM user_indexes",
        'index_columns':"SELECT index_name,table_name,column_name,column_position,descend FROM user_ind_columns",
        'views':"SELECT view_name,text FROM user_views",
        'triggers':"SELECT trigger_name,trigger_type,triggering_event,table_name,status,trigger_body FROM user_triggers",
        'routines':"SELECT name,type,line,text FROM user_source",
        'sequences':"SELECT sequence_name,min_value,max_value,increment_by,cycle_flag,order_flag,cache_size,last_number FROM user_sequences",
    } if lane=='oracle' else {
        'columns':"SELECT table_name,column_name,data_type,character_maximum_length,numeric_precision,numeric_scale,is_nullable,column_default,is_identity,is_generated,generation_expression FROM information_schema.columns WHERE table_schema='adempiere'",
        'constraints':"SELECT c.relname table_name,con.conname constraint_name,pg_get_constraintdef(con.oid) definition FROM pg_constraint con JOIN pg_namespace n ON n.oid=con.connamespace LEFT JOIN pg_class c ON c.oid=con.conrelid WHERE n.nspname='adempiere'",
        'indexes':"SELECT tablename,indexname,indexdef FROM pg_indexes WHERE schemaname='adempiere'",
        'views':"SELECT viewname,definition FROM pg_views WHERE schemaname='adempiere'",
        'triggers':"SELECT c.relname table_name,t.tgname trigger_name,pg_get_triggerdef(t.oid) definition FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='adempiere'",
        'routines':"SELECT p.proname,pg_get_function_identity_arguments(p.oid) arguments,pg_get_functiondef(p.oid) definition FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='adempiere' AND p.prokind<>'a'",
        'sequences':"SELECT sequencename,start_value,min_value,max_value,increment_by,cycle,cache_size,last_value FROM pg_sequences WHERE schemaname='adempiere'",
    })
    structure={name:query(connection,sql) for name,sql in structure_queries.items()}
    result=seal({'schema_version':'1.0','artifact_type':'lightyear-native-state-observation','lane':lane,
                 'observed_at':datetime.now(timezone.utc).isoformat(),'evidence_class':'native-database-observation',
                 'row_capture_scope':'all ordinary base tables, all columns, all rows; no sampling',
                 'structure_query_sha256':digest(structure_queries),'tables':rows,'structure':structure})
    (output/'state.json').write_text(json.dumps(result,separators=(',',':')),encoding='utf-8')
    return result


def observed_delta(before, after):
    verify(before);verify(after)
    require(before['lane']==after['lane'], 'Cross-lane delta')
    require(before['evidence_class']==after['evidence_class']=='native-database-observation', 'Non-native state')
    require(before['structure_query_sha256']==after['structure_query_sha256'], 'Changed observation contract')
    tables={}
    for name in sorted(set(before['tables'])|set(after['tables'])):
        b=before['tables'].get(name);a=after['tables'].get(name)
        delta=row_delta(b['row_multiset'] if b else {},a['row_multiset'] if a else {})
        if delta['added'] or delta['removed'] or bool(b)!=bool(a):
            tables[name]={'exists_before':b is not None,'exists_after':a is not None,**delta}
    structure={}
    for kind in sorted(set(before['structure'])|set(after['structure'])):
        b={digest(row):row for row in before['structure'].get(kind,[])}
        a={digest(row):row for row in after['structure'].get(kind,[])}
        if b!=a:structure[kind]={'removed':[b[k] for k in sorted(b.keys()-a.keys())],'added':[a[k] for k in sorted(a.keys()-b.keys())]}
    return {'tables':tables,'structure':structure}


def compare_observations(before,after,execution):
    require(set(before)==set(after)==set(execution)=={'oracle','postgresql'}, 'Both lanes required')
    require(all(before[k]['lane'] == after[k]['lane'] == k for k in before), 'Mislabeled observation lane')
    deltas={lane:observed_delta(before[lane],after[lane]) for lane in before}
    same_rows=deltas['oracle']['tables']==deltas['postgresql']['tables']
    business_rows={lane:{k:v for k,v in d['tables'].items() if k!='ad_migrationscript'} for lane,d in deltas.items()}
    schema_change=any(d['structure'] for d in deltas.values())
    successful=all(e['returncode']==0 for e in execution.values())
    # Even identical observed deltas on public seeds are not application proof.
    status=('execution-failed' if not successful else 'observed-effects-differ' if not same_rows else
            'observed-rows-match-structure-review-required' if schema_change else 'observed-effects-match')
    return seal({'schema_version':'1.0','artifact_type':'lightyear-native-migration-comparison','status':status,
        'evidence_class':'native-database-observation','execution':execution,'deltas':deltas,
        'state_sha256':{lane:{'before':before[lane]['content_sha256'],'after':after[lane]['content_sha256']} for lane in before},
        'row_effects_match':same_rows,'structural_change_requires_review':schema_change,
        'non_registration_row_effects_match':business_rows['oracle']==business_rows['postgresql'],
        'registration_effects_retained':True,
        'application_equivalence':False,'historical_upgrade_equivalence':False,
        'scope':'observed effects on these imported reference seeds; initial states may differ; no runtime values suppressed'})
