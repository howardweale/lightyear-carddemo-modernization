"""Collector revision 2: configurable target schemas, procedural module scope.
Native qualification required before equivalence; v1 remains immutable for replay.

Measured coverage with retained native trace/profiler inputs and offline replay.

Counts describe procedural statements/edges, not SQL expression or query-plan
coverage. Missing edges remain missing; a successful call is never coverage.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET
from .capture import query


def sha(raw): return hashlib.sha256(raw).hexdigest()


def _inside(offset, span):
    return span['start_utf16'] <= offset < span['start_utf16']+span['length_utf16']


def sql_summary(evidence):
    tree=ET.fromstring(evidence['ring_xml'])
    if tree.get('truncated','0')!='0' or int(tree.get('droppedCount','0')) or evidence['dropped_events']:
        raise ValueError('coverage-events-lost')
    events=[]
    for event in tree.findall('event'):
        values={x.get('name'):x.findtext('value') for x in event.findall('data')}
        sequence=event.find("action[@name='event_sequence']/value")
        if sequence is None: raise ValueError('coverage-sequence-missing')
        events.append({'kind':event.get('name'),'values':values,'sequence':int(sequence.text)})
    events.sort(key=lambda x:x['sequence'])
    if len({e['sequence'] for e in events})!=len(events): raise ValueError('coverage-sequence-duplicate')
    modules=[]
    for module in evidence['modules']:
        source=module['definition'];parsed=module['parsed']
        if parsed['input_sha256']!=sha(source.encode()) or not parsed['parsed']:
            raise ValueError('coverage-parser-binding')
        catalogue=parsed['coverage_catalogue']
        if catalogue['schema']!='tsql-scriptdom-coverage/1':raise ValueError('coverage-catalogue')
        starts=[];module_events=[]
        for event in events:
            v=event['values']
            if int(v.get('object_id','-1'))!=module['object_id']:continue
            offset=int(v['offset'])
            if offset<0 or offset%2:raise ValueError('coverage-offset')
            module_events.append((event['kind'],offset//2))
            if event['kind']=='sp_statement_starting':starts.append(offset//2)
        statements=catalogue['statements'];hits=[]
        for offset in starts:
            candidates=[s for s in statements if _inside(offset,s)]
            if candidates:
                site=min(candidates,key=lambda x:x['length_utf16'])
                hits.append(site['start_utf16'])
        hit=set(hits);edges=[]
        for b in catalogue['branches']:
            own=b['statement']['start_utf16']
            then=any(_inside(v,b['then_span']) for v in starts)
            otherwise=b['else_span'] is not None and any(_inside(v,b['else_span']) for v in starts)
            # A false edge without an ELSE needs a native condition event and
            # a later statement beyond the complete conditional. Never infer
            # entry merely because a parent call completed.
            if not otherwise:
                # Evaluate each visit separately: a loop can take both edges.
                # Require the condition's native completion before an adjacent
                # statement outside its body; a throwing predicate proves nothing.
                for index,(kind,offset) in enumerate(module_events):
                    if kind!='sp_statement_completed' or offset!=own:continue
                    following=next((v for k,v in module_events[index+1:] if k=='sp_statement_starting'),None)
                    if following is not None and following>=own+b['statement']['length_utf16']:
                        otherwise=True
            edges.extend([{'site':own,'edge':'true','hit':then}, {'site':own,'edge':'false','hit':bool(otherwise)}])
        errors=[{'site':h['span']['start_utf16'],
                 'hit':any(_inside(v,h['span']) for v in starts)} for h in catalogue['handlers']]
        modules.append({'name':module['name'],'source_sha256':parsed['input_sha256'],
            'statements_total':len(statements),'statements_hit':len(hit),
            'uncovered_lines':sorted({s['line'] for s in statements if s['start_utf16'] not in hit}),
            'branches':edges,'error_paths':errors,
            'native_started_offsets_utf16':starts})
    return summarize('sqlserver-extended-events-scriptdom/1',modules)


def pg_summary(evidence):
    modules=[]
    for module in evidence['modules']:
        before=module['before'];after=module['after']
        # Profiler denominators are materialized before the tested call.
        ids=lambda rows:{r['stmtid'] for r in rows}
        if ids(before)!=ids(after) or len(ids(before))!=len(before):raise ValueError('profiler-catalogue-changed')
        if any(r['exec_stmts'] for r in before): raise ValueError('profiler-not-fresh')
        statements=[r for r in after if r['stmtname']!='statement block']
        # Native profiler reports procedural branch fraction; retain its exact
        # fraction separately instead of manufacturing integer denominators.
        fraction=module['branch_fraction']
        if not isinstance(fraction,(int,float)) or not 0<=fraction<=1:raise ValueError('profiler-branch-fraction')
        modules.append({'name':module['name'],'source_sha256':sha(module['definition'].encode()),
            'statements_total':len(statements),'statements_hit':sum((r['exec_stmts'] or 0)>0 for r in statements),
            'uncovered_lines':sorted({r['lineno'] for r in statements if not r['exec_stmts']}),
            'branches':None,'branch_fraction':fraction,
            # Version 2.10 does not expose handler identities in this table.
            # Its branch denominator includes exception-handler bodies. Requiring
            # ALL native branches conservatively proves all handlers; below 1.0
            # we cannot distinguish an unhit IF from an unhit handler.
            'error_paths':[{'site':'all-native-branches-including-handlers','hit':fraction==1.0}],
            'error_path_resolution':'aggregate conservative proof; not individual handler attribution'})
    return summarize('plpgsql-check-native-profiler/1',modules)


def summarize(collector,modules):
    total=sum(m['statements_total'] for m in modules);hit=sum(m['statements_hit'] for m in modules)
    if not modules or not total:raise ValueError('empty-coverage-catalogue')
    fractions=[]
    for m in modules:
        if m.get('branches') is None: fractions.append(m['branch_fraction'])
        else: fractions.append(sum(e['hit'] for e in m['branches'])/len(m['branches']) if m['branches'] else 1.0)
    missing=[{'module':m['name'],'site':e['site']} for m in modules for e in m['error_paths'] if not e['hit']]
    return {'schema':'tsql-measured-coverage/2','collector':collector,'modules':modules,
        'statement_fraction':hit/total,'minimum_module_branch_fraction':min(fractions),
        'missing_error_paths':missing,'eligible':hit/total>=.90 and min(fractions)>=.80 and not missing,
        'scope':'procedural statements/edges and CATCH/EXCEPTION paths; SQL expression branches excluded',
        'execution_success_is_coverage':False}


class SqlCoverage:
    def __init__(self,connection,name,bridge):
        if not name.replace('_','').isalnum():raise ValueError('coverage-session-name')
        self.c,self.name=connection,name
        self.modules=[]
        self.excluded_views=[{'name':schema+'.'+name_,'definition_sha256':sha(definition.encode())}
            for schema,name_,definition in query(connection,"""SELECT SCHEMA_NAME(o.schema_id),o.name,m.definition
FROM sys.sql_modules m JOIN sys.objects o ON o.object_id=m.object_id WHERE o.is_ms_shipped=0 AND o.type='V' ORDER BY o.object_id""")]
        for oid,schema,name_,definition in query(connection,"""SELECT o.object_id,SCHEMA_NAME(o.schema_id),o.name,m.definition
FROM sys.sql_modules m JOIN sys.objects o ON o.object_id=m.object_id WHERE o.is_ms_shipped=0 AND o.type IN ('P','FN','TF','TR') ORDER BY o.object_id"""):
            p=subprocess.run(['dotnet',str(bridge)],input=definition.encode(),capture_output=True,timeout=30)
            parsed=json.loads(p.stdout)
            if p.returncode or not parsed['parsed']:raise ValueError('coverage-source-parse')
            self.modules.append({'object_id':oid,'name':schema+'.'+name_,'definition':definition,'parsed':parsed})
        self.bridge_sha256=sha(Path(bridge).read_bytes())
        self.spid=query(connection,'SELECT @@SPID')[0][0]
    def start(self):
        sql='CREATE EVENT SESSION ['+self.name+'] ON SERVER '+','.join(
            'ADD EVENT sqlserver.'+event+'(ACTION(package0.event_sequence) WHERE ([sqlserver].[session_id]=('+str(self.spid)+')))'
            for event in ('sp_statement_starting','sp_statement_completed'))
        sql+=' ADD TARGET package0.ring_buffer(SET max_memory=4096) WITH (MAX_MEMORY=4096 KB,EVENT_RETENTION_MODE=NO_EVENT_LOSS,MAX_DISPATCH_LATENCY=1 SECONDS)'
        self.c.cursor().execute(sql)
        self.c.cursor().execute('ALTER EVENT SESSION ['+self.name+'] ON SERVER STATE=START')
    def finish(self, preserve=None):
        try:
            rows=query(self.c,"""SELECT CONVERT(nvarchar(max),t.target_data),s.dropped_event_count
FROM sys.dm_xe_sessions s JOIN sys.dm_xe_session_targets t ON t.event_session_address=s.address
WHERE s.name=%s AND t.target_name='ring_buffer'""",(self.name,))
            if len(rows)!=1:raise ValueError('coverage-target-missing')
            raw={'schema':'tsql-sqlserver-coverage-input/2','modules':self.modules,
                 'excluded_views':self.excluded_views,
                 'bridge_sha256':self.bridge_sha256,'ring_xml':rows[0][0],'dropped_events':rows[0][1]}
            if preserve: preserve(raw)
            return {'raw':raw,'summary':sql_summary(raw)}
        finally:
            self.c.cursor().execute('DROP EVENT SESSION ['+self.name+'] ON SERVER')


class PgCoverage:
    def __init__(self,connection,schemas=('dbo',)):
        if not schemas or any(not isinstance(s,str) or not s for s in schemas):raise ValueError('coverage-schemas')
        self.c=connection;self.modules=[];self.schemas=tuple(schemas)
    def start(self):
        self.c.cursor().execute("LOAD 'plpgsql_check'; SELECT plpgsql_check_profiler(true); SELECT plpgsql_profiler_reset_all()")
        self.version=query(self.c,"SELECT extversion FROM pg_extension WHERE extname='plpgsql_check'")[0][0]
        for oid,name,definition in query(self.c,"""SELECT p.oid,p.oid::regprocedure::text,pg_get_functiondef(p.oid)
FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace JOIN pg_language l ON l.oid=p.prolang
WHERE n.nspname = ANY(%s) AND l.lanname='plpgsql' ORDER BY p.oid""",(list(self.schemas),)):
            self.modules.append({'oid':oid,'name':name,'definition':definition,'before':self.statements(oid)})
    def statements(self,oid):
        return [json.loads(r[0]) for r in query(self.c,'SELECT row_to_json(p)::text FROM plpgsql_profiler_function_statements_tb(%s::oid) p',(oid,))]
    def finish(self, preserve=None):
        for m in self.modules:
            m['after']=self.statements(m['oid'])
            m['branch_fraction']=float(query(self.c,'SELECT plpgsql_coverage_branches(%s::oid)',(m['oid'],))[0][0])
        raw={'schema':'tsql-postgresql-coverage-input/2','extension_version':self.version,'modules':self.modules,
             'schemas':list(self.schemas)}
        if preserve: preserve(raw)
        return {'raw':raw,'summary':pg_summary(raw)}


def replay_coverage(record):
    raw=record['raw']
    if raw['schema'] not in ('tsql-sqlserver-coverage-input/2','tsql-postgresql-coverage-input/2'):
        raise ValueError('coverage-schema')
    result=sql_summary(raw) if raw['schema']=='tsql-sqlserver-coverage-input/2' else pg_summary(raw)
    if result!=record['summary']:raise ValueError('coverage-replay-mismatch')
    return result
