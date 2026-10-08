"""Native module inventory and conservative dependency closure, recorded per pair.

All user modules are retained, including uncalled modules. Dynamic SQL, encrypted
modules and unresolved cross-database edges never acquire closure from a name.
"""
from .capture import query
from .native_evidence import canonical,sha

SQL_MODULES="""SELECT o.object_id,SCHEMA_NAME(o.schema_id),o.name,o.type,m.definition
FROM sys.objects o LEFT JOIN sys.sql_modules m ON m.object_id=o.object_id
WHERE o.is_ms_shipped=0 AND o.type IN ('P','PC','FN','IF','TF','FS','FT','TR','TA','V')
ORDER BY o.object_id"""
SQL_EDGES="""SELECT d.referencing_id,d.referenced_id,d.referenced_server_name,d.referenced_database_name,
d.referenced_schema_name,d.referenced_entity_name,d.is_caller_dependent,d.is_ambiguous,
COALESCE(o.is_ms_shipped,0)
FROM sys.sql_expression_dependencies d LEFT JOIN sys.objects o ON o.object_id=d.referenced_id
WHERE d.referencing_id IN (SELECT object_id FROM sys.objects WHERE is_ms_shipped=0)
ORDER BY d.referencing_id,d.referenced_id,d.referenced_entity_name"""
SQL_SYNONYMS='SELECT object_id,SCHEMA_NAME(schema_id),name,base_object_name FROM sys.synonyms ORDER BY object_id'
PG_MODULES="""SELECT p.oid::bigint,n.nspname,p.proname,p.prokind::text,pg_get_functiondef(p.oid)
FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
WHERE n.nspname NOT IN ('pg_catalog','information_schema') AND n.nspname NOT LIKE 'pg_toast%%'
AND p.prokind IN ('f','p') AND NOT EXISTS
(SELECT 1 FROM pg_depend d WHERE d.classid='pg_proc'::regclass AND d.objid=p.oid AND d.deptype='e') ORDER BY p.oid"""
PG_VIEWS="""SELECT c.oid::bigint,n.nspname,c.relname,c.relkind::text,pg_get_viewdef(c.oid,true)
FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
WHERE c.relkind IN ('v','m') AND n.nspname NOT IN ('pg_catalog','information_schema') ORDER BY c.oid"""
PG_TRIGGERS="""SELECT t.oid::bigint,n.nspname,t.tgname,'trigger',pg_get_triggerdef(t.oid,true)
FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid JOIN pg_namespace n ON n.oid=c.relnamespace
WHERE NOT t.tgisinternal ORDER BY t.oid"""

PG_EDGES="""SELECT d.classid::regclass::text || ':' || d.objid::text,
 d.refclassid::regclass::text || ':' || d.refobjid::text,NULL,NULL,r.schema,r.name,false,false,COALESCE(r.schema IN ('pg_catalog','information_schema'),false)
FROM pg_depend d CROSS JOIN LATERAL pg_identify_object(d.refclassid,d.refobjid,d.refobjsubid) r WHERE (d.classid='pg_proc'::regclass AND d.objid IN
 (SELECT p.oid FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname NOT IN ('pg_catalog','information_schema')))
 OR (d.classid='pg_rewrite'::regclass AND d.objid IN
 (SELECT r.oid FROM pg_rewrite r JOIN pg_class c ON c.oid=r.ev_class JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname NOT IN ('pg_catalog','information_schema')))
 OR (d.classid='pg_trigger'::regclass AND d.objid IN (SELECT oid FROM pg_trigger WHERE NOT tgisinternal))
ORDER BY 1,2"""
SQL_OBJECTS='SELECT object_id,SCHEMA_NAME(schema_id),name,type FROM sys.objects WHERE is_ms_shipped=0 ORDER BY object_id'

def capture(connection,engine,bridge=None):
    if engine=='sqlserver':
        modules=query(connection,SQL_MODULES);edges=query(connection,SQL_EDGES);synonyms=query(connection,SQL_SYNONYMS)
    elif engine=='postgresql':
        modules=query(connection,PG_MODULES)+query(connection,PG_VIEWS)+query(connection,PG_TRIGGERS)
        edges=query(connection,PG_EDGES);synonyms=[]
    else:raise ValueError('dependency-engine')
    objects=query(connection,SQL_OBJECTS) if engine=='sqlserver' else []
    parsed={}
    if engine=='sqlserver' and bridge:
        import subprocess,json
        for identity,_,_,_,definition in modules:
            if not definition:continue
            result=subprocess.run(['dotnet',str(bridge)],input=definition.encode(),capture_output=True,timeout=30)
            if result.returncode==0:
                ast=json.loads(result.stdout);parsed[str(identity)]=ast
                for e in ast.get('semantic_catalogue',{}).get('exec_contracts',[]):
                    if not e.get('called_parts') or e['called_parts'][-1].lower()!='sp_executesql' or e.get('literal_start_utf16') is None:continue
                    start=e['literal_start_utf16'];length=e['literal_length_utf16']
                    literal=definition.encode('utf-16-le')[start*2:(start+length)*2].decode('utf-16-le')
                    if literal[:1].lower()=='n':literal=literal[1:]
                    if not literal.startswith("'") or not literal.endswith("'"):raise ValueError('literal-exec-span')
                    sql=literal[1:-1].replace("''", "'")
                    if sha(sql.encode())!=e['literal_sql_sha256']:raise ValueError('literal-exec-hash')
                    nested=subprocess.run(['dotnet',str(bridge)],input=sql.encode(),capture_output=True,timeout=30)
                    if nested.returncode==0:e['literal_parsed']=json.loads(nested.stdout)
    body=dict(schema='tsql-native-dependencies/2',engine=engine,modules=modules,edges=edges,synonyms=synonyms,objects=objects,parsed=parsed,
              scope='all user procedures, functions, views, triggers and synonyms; not only visited modules')
    body['content_sha256']=sha(canonical(body));return body

def assess(record):
    body={k:v for k,v in record.items() if k!='content_sha256'}
    if record.get('schema') not in ('tsql-native-dependencies/1','tsql-native-dependencies/2') or sha(canonical(body))!=record.get('content_sha256'):
        raise ValueError('dependency-catalogue-binding')
    issues=[]
    ids=[row[0] for row in record['modules']]
    if len(ids)!=len(set(ids)):raise ValueError('duplicate-module-identity')
    from .inventory import scan
    for identity,schema,name,kind,definition in record['modules']:
        if not isinstance(definition,str) or not definition.strip():issues.append('unreadable-or-native-module');continue
        hints=scan(definition)
        if hints['dynamic_sql']:
            parsed=record.get('parsed',{}).get(str(identity))
            execs=parsed.get('semantic_catalogue',{}).get('exec_contracts',[]) if parsed else []
            if not parsed or parsed['input_sha256']!=sha(definition.encode()) or not execs or not all(e['no_results_proven'] for e in execs):
                issues.append('dynamic-module-dependency')
        if hints['unsupported_features']:issues.append('unsupported-module-feature')
    for row in record['edges']:
        caller,target,server,database,schema,name,dependent,ambiguous,system=row
        if server or database:issues.append('cross-database-module-dependency')
        if dependent or ambiguous:issues.append('late-bound-module-dependency')
        if target is None and not system:
            caller_kind=next((m[3] for m in record['modules'] if m[0]==caller),None)
            if not (caller_kind in ('TR','TA') and schema is None and name and name.lower() in ('inserted','deleted')):
                issues.append('unresolved-module-dependency')
    # Synonyms require catalogue name resolution. Preserve the exact definitions,
    # but never infer that a textual local-looking target grants closure.
    names={(s.lower(),n.lower()):oid for oid,s,n,_ in record.get('objects',[])}
    synonym_targets={oid:base for oid,_,_,base in record['synonyms']}
    for identity,_,_,base in record['synonyms']:
        seen=set();current=identity
        while current in synonym_targets:
            if current in seen:issues.append('synonym-cycle');break
            seen.add(current)
            # Exact local two-part names only. Escaped/dotted identifiers and
            # cross-database references remain refused rather than guessed.
            import re
            match=re.fullmatch(r'\[?([A-Za-z_][A-Za-z_0-9]*)\]?\.\[?([A-Za-z_][A-Za-z_0-9]*)\]?',synonym_targets[current])
            if not match or tuple(x.lower() for x in match.groups()) not in names:
                issues.append('synonym-target-resolution-required');break
            current=names[tuple(x.lower() for x in match.groups())]
    return dict(catalogue_sha256=record['content_sha256'],modules=len(ids),issues=sorted(set(issues)),
                closed=not issues,claim='catalogue closure only; callee result-origin remains separately gated')
