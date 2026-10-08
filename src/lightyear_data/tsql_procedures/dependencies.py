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

def capture(connection,engine):
    if engine=='sqlserver':
        modules=query(connection,SQL_MODULES);edges=query(connection,SQL_EDGES);synonyms=query(connection,SQL_SYNONYMS)
    elif engine=='postgresql':
        modules=query(connection,PG_MODULES)+query(connection,PG_VIEWS)+query(connection,PG_TRIGGERS)
        edges=[];synonyms=[]
    else:raise ValueError('dependency-engine')
    body=dict(schema='tsql-native-dependencies/1',engine=engine,modules=modules,edges=edges,synonyms=synonyms,
              scope='all user procedures, functions, views, triggers and synonyms; not only visited modules')
    body['content_sha256']=sha(canonical(body));return body

def assess(record):
    body={k:v for k,v in record.items() if k!='content_sha256'}
    if record.get('schema')!='tsql-native-dependencies/1' or sha(canonical(body))!=record.get('content_sha256'):
        raise ValueError('dependency-catalogue-binding')
    issues=[]
    ids=[row[0] for row in record['modules']]
    if len(ids)!=len(set(ids)):raise ValueError('duplicate-module-identity')
    from .inventory import scan
    for identity,schema,name,kind,definition in record['modules']:
        if not isinstance(definition,str) or not definition.strip():issues.append('unreadable-or-native-module');continue
        hints=scan(definition)
        if hints['dynamic_sql']:issues.append('dynamic-module-dependency')
        if hints['unsupported_features']:issues.append('unsupported-module-feature')
    for row in record['edges']:
        caller,target,server,database,schema,name,dependent,ambiguous,system=row
        if server or database:issues.append('cross-database-module-dependency')
        if dependent or ambiguous:issues.append('late-bound-module-dependency')
        if target is None and not system:issues.append('unresolved-module-dependency')
    # Synonyms require catalogue name resolution. Preserve the exact definitions,
    # but never infer that a textual local-looking target grants closure.
    if record['synonyms']:issues.append('synonym-target-resolution-required')
    return dict(catalogue_sha256=record['content_sha256'],modules=len(ids),issues=sorted(set(issues)),
                closed=not issues,claim='catalogue closure only; callee result-origin remains separately gated')
