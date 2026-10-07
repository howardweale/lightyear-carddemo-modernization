"""Write a NEW public coverage-control corpus, before its native run.

This is collector qualification, not extra trap successes. Sources, expected
coverage outcomes and plan are retained whether the collector passes or fails.
"""
import json
from pathlib import Path
import sys
from copy import deepcopy
from lightyear_data.tsql_procedures.corpus import corpus,COMMON_SOURCE,COMMON_TARGET
from lightyear_data.tsql_procedures.native_evidence import sha,write


def controls(root):
    target=root/'data-modernization/tsql-procedures'
    target.mkdir(parents=True,exist_ok=False)
    source=lambda body:'CREATE PROCEDURE dbo.trap AS BEGIN SET NOCOUNT ON; '+body+' END;\nGO\n'
    pg=lambda body:'CREATE FUNCTION dbo.trap() RETURNS TABLE(value text) LANGUAGE plpgsql AS $$ BEGIN '+body+' END; $$;\n'
    rows=[
      ('straight',source("SELECT 'ok' AS value;"),pg("RETURN QUERY SELECT 'ok'::text;"),'eligible'),
      ('both-edges',source("DECLARE @i int=0; WHILE @i<2 BEGIN IF @i=0 INSERT dbo.effects VALUES(1,1); ELSE INSERT dbo.effects VALUES(2,2); SET @i=@i+1; END; SELECT 'ok' AS value;"),
       pg("FOR i IN 0..1 LOOP IF i=0 THEN INSERT INTO dbo.effects VALUES(1,1); ELSE INSERT INTO dbo.effects VALUES(2,2); END IF; END LOOP; RETURN QUERY SELECT 'ok'::text;"),'both-edges'),
      ('missing-edge',source("IF 1=0 INSERT dbo.effects VALUES(1,1); SELECT 'ok' AS value;"),
       pg("IF false THEN INSERT INTO dbo.effects VALUES(1,1); END IF; RETURN QUERY SELECT 'ok'::text;"),'ineligible'),
      ('handler-hit',source("BEGIN TRY DECLARE @z int=0,@n int; SET @n=1/@z; END TRY BEGIN CATCH INSERT dbo.effects VALUES(1,1); END CATCH; SELECT 'ok' AS value;"),
       pg("BEGIN PERFORM 1/0; EXCEPTION WHEN division_by_zero THEN INSERT INTO dbo.effects VALUES(1,1); END; RETURN QUERY SELECT 'ok'::text;"),'handler-hit'),
      ('handler-missing',source("BEGIN TRY SELECT 'ok' AS value; END TRY BEGIN CATCH INSERT dbo.effects VALUES(1,1); END CATCH;"),
       pg("BEGIN RETURN QUERY SELECT 'ok'::text; EXCEPTION WHEN division_by_zero THEN INSERT INTO dbo.effects VALUES(1,1); END;"),'handler-missing'),
      ('scalar-declaration',source("DECLARE @x int; SET @x=7; SELECT CONVERT(varchar(20),@x) AS value;"),
       pg("RETURN QUERY SELECT '7'::text;"),'eligible'),
      ('table-declaration',source("DECLARE @t TABLE(n int); INSERT @t VALUES(7); SELECT CONVERT(varchar(20),n) AS value FROM @t;"),
       pg("RETURN QUERY SELECT '7'::text;"),'eligible'),
    ]
    items=[]
    for name,s,p,expected in rows:
        item=deepcopy(corpus()[0]);item['id']='coverage-'+name;item['assets']={};item['trap_family']=1
        for key in list(item):
            if key.endswith('_sql') or key.endswith('_setup'):del item[key]
        item['collector_control_expected']=expected
        for role,sql in [('source',s),('correct',p),('wrong',p),('source-setup',COMMON_SOURCE),('target-setup',COMMON_TARGET),('wrong-setup',COMMON_TARGET)]:
            f=target/(item['id']+'-'+role+'.sql');f.write_text(sql,encoding='utf-8',newline='\n')
            item['assets'][role]={'path':f.relative_to(root).as_posix(),'sha256':sha(f.read_bytes())}
        items.append(item)
    write(target/'corpus.json',{'schema':'tsql-coverage-control-corpus/1','procedures':items,'model_calls':0})


if __name__=='__main__':controls(Path(sys.argv[1]).resolve())
