"""Authored public SQL traps; expected outcomes are hypotheses until paired native runs.

No copied vendor sample code, engine calls, container calls or model calls.
Regeneration is deterministic; variant SQL and setup bytes are all hash-bound.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from lightyear_data.contracts import canonical_bytes, seal
from .ledger import FAMILIES, build_ledger

ROOT_DIR="data-modernization/tsql-procedures"
COMMON_SOURCE="CREATE TABLE dbo.effects(id int NOT NULL PRIMARY KEY, amount int NOT NULL);\nGO\n"
COMMON_TARGET="CREATE SCHEMA IF NOT EXISTS dbo;\nCREATE TABLE dbo.effects(id integer PRIMARY KEY, amount integer NOT NULL);\n"


def corpus():
    rows=[]
    def add(name,family,source,correct,wrong,mutation,*,ss="",ps="",ws=None,convention=None,parameters=None):
        rows.append(dict(id=name,trap_family=family,trap_name=FAMILIES[family][0],
            source_sql=source,correct_sql=correct,wrong_sql=wrong,
            source_setup=COMMON_SOURCE+ss,target_setup=COMMON_TARGET+ps,
            wrong_setup=COMMON_TARGET+(ps if ws is None else ws),
            mutation=mutation,parameters=parameters or {},
            calling_convention=convention or {"source":"EXEC dbo.trap","target":"SELECT * FROM dbo.trap()",
                "result_columns":[{"name":"value","canonical_type":"variable-character"}],
                "source_return_code":"capture-TDS-return-status","target_return_code":"mapped-default-zero",
                "caller_transaction":"autocommit; never outer rollback"},
            expected={"correct":"insufficient-evidence" if family in (18,25) else "equivalent",
                      "wrong":"insufficient-evidence" if family in (18,25) else "divergent",
                      "policy_required":family in (18,25),"trap_family":family},
            cases=[{"id":"boundary-01","state":"empty-public-schema","parameters":parameters or {},
                    "clock_policy":{"mode":"real-clock","time-dependent":False},
                    "source_session":{"ANSI_NULLS":"ON","ANSI_WARNINGS":"ON","ARITHABORT":"ON",
                        "CONCAT_NULL_YIELDS_NULL":"ON","QUOTED_IDENTIFIER":"ON","NOCOUNT":"ON",
                        "XACT_ABORT":"OFF","DATEFIRST":7,"DATEFORMAT":"mdy","LANGUAGE":"us_english"},
                    "target_session":{"TimeZone":"UTC","standard_conforming_strings":"on"},
                    "coverage_required":{"statements":0.9,"branches":0.8,"all_reachable_error_paths":True},
                    "repeated_runs":5 if family in (18,25) else 1}],
            native_status="not-run"))
    def sp(body,parameters=""):
        return "CREATE OR ALTER PROCEDURE dbo.trap"+(" "+parameters if parameters else "")+f"\nAS\nBEGIN\n SET NOCOUNT ON;\n {body.rstrip()}\nEND;\nGO\n"
    def fn(body,declare=""):
        return "CREATE OR REPLACE FUNCTION dbo.trap() RETURNS TABLE(value text) LANGUAGE plpgsql AS $trap$\n"+("DECLARE "+declare+"\n" if declare else "")+"BEGIN\n "+body+"\nEND;\n$trap$;\n"
    def scalar(name,family,s,p,w,mutation,pre="",post=""):
        add(name,family,sp(pre+" SELECT CONVERT(varchar(200), ("+s+")) AS value; "+post),
            fn("RETURN QUERY SELECT ("+p+")::text;"),fn("RETURN QUERY SELECT ("+w+")::text;"),mutation)
    scalar("ci-equality",1,"CASE WHEN 'Alpha' COLLATE Latin1_General_100_CI_AS = 'alpha' THEN 1 ELSE 0 END",
           "CASE WHEN lower('Alpha')=lower('alpha') THEN 1 ELSE 0 END",
           "CASE WHEN 'Alpha'='alpha' THEN 1 ELSE 0 END","Dropped declared case folding (ASCII fixture only).")
    scalar("ci-join",1,"SELECT COUNT(*) FROM (VALUES ('A'),('a')) a(v) JOIN (VALUES ('A')) b(v) ON a.v COLLATE Latin1_General_100_CI_AS=b.v",
           "SELECT count(*) FROM (VALUES ('A'),('a')) a(v) JOIN (VALUES ('A')) b(v) ON lower(a.v)=lower(b.v)",
           "SELECT count(*) FROM (VALUES ('A'),('a')) a(v) JOIN (VALUES ('A')) b(v) ON a.v=b.v","Dropped case-insensitive join.")
    scalar("ci-group",1,"SELECT COUNT(*) FROM (SELECT v COLLATE Latin1_General_100_CI_AS AS k FROM (VALUES ('A'),('a')) x(v) GROUP BY v COLLATE Latin1_General_100_CI_AS) g",
           "SELECT count(*) FROM (SELECT lower(v) FROM (VALUES ('A'),('a')) x(v) GROUP BY lower(v)) g",
           "SELECT count(*) FROM (SELECT v FROM (VALUES ('A'),('a')) x(v) GROUP BY v) g","Grouped case variants separately.")
    scalar("ci-distinct",1,"SELECT COUNT(DISTINCT v COLLATE Latin1_General_100_CI_AS) FROM (VALUES ('A'),('a')) x(v)",
           "SELECT count(DISTINCT lower(v)) FROM (VALUES ('A'),('a')) x(v)",
           "SELECT count(DISTINCT v) FROM (VALUES ('A'),('a')) x(v)","Dropped folding for DISTINCT.")
    unique_source=sp("INSERT dbo.names(v) VALUES ('A'); BEGIN TRY INSERT dbo.names(v) VALUES ('a'); END TRY BEGIN CATCH IF ERROR_NUMBER() NOT IN (2601,2627) THROW; END CATCH; SELECT CONVERT(varchar(20),COUNT(*)) AS value FROM dbo.names;")
    unique_target=fn("INSERT INTO dbo.names(v) VALUES ('A'); BEGIN INSERT INTO dbo.names(v) VALUES ('a'); EXCEPTION WHEN unique_violation THEN NULL; END; RETURN QUERY SELECT count(*)::text FROM dbo.names;")
    add("ci-unique",1,unique_source,unique_target,unique_target,"Replaced case-folded unique index with case-sensitive index.",
        ss="CREATE TABLE dbo.names(v varchar(20) COLLATE Latin1_General_100_CI_AS NOT NULL UNIQUE);\nGO\n",
        ps="CREATE TABLE dbo.names(v varchar(20) NOT NULL); CREATE UNIQUE INDEX names_uq ON dbo.names(lower(v));\n",
        ws="CREATE TABLE dbo.names(v varchar(20) NOT NULL); CREATE UNIQUE INDEX names_uq ON dbo.names(v);\n")
    for typ in ("char","varchar"):
        scalar("trailing-"+typ,2,f"CASE WHEN CAST('A ' AS {typ}(3))=CAST('A' AS {typ}(3)) THEN 1 ELSE 0 END",
               "CASE WHEN rtrim('A ')=rtrim('A') THEN 1 ELSE 0 END",
               "CASE WHEN 'A '='A' THEN 1 ELSE 0 END","Compared trailing padding as significant.")
    scalar("len",3,"LEN(' A  ')","length(rtrim(' A  '))","length(' A  ')","Counted trailing spaces.")
    scalar("integer-division",4,"7/2","7/2","7.0/2","Promoted integer division to decimal.")
    scalar("type-precedence",4,"'2'+3","CAST('2' AS integer)+3","'2'||3::text","Concatenated instead of numeric addition.")
    scalar("isnull-length",5,"ISNULL(CAST(NULL AS varchar(3)),'abcdef')",
           "left(coalesce(NULL::text,'abcdef'),3)","coalesce(NULL::text,'abcdef')","Lost first-argument truncation.")
    scalar("empty-int",6,"CAST('' AS int)","coalesce(nullif('',''),'0')::integer","nullif('','')::integer","Mapped empty to NULL instead of zero.")
    scalar("empty-date",6,"CONVERT(varchar(10),CAST('' AS datetime),23)",
           "to_char(coalesce(nullif('','')::timestamp,timestamp '1900-01-01'),'YYYY-MM-DD')",
           "to_char(nullif('','')::timestamp,'YYYY-MM-DD')","Mapped empty to NULL instead of base date.")
    for suffix in ("001","002"):
        date="2026-10-01 00:00:00."+suffix
        p=f"to_char(timestamp '2026-10-01'+(round({int(suffix)}::numeric*0.3)/0.3)*interval '1 millisecond','YYYY-MM-DD HH24:MI:SS.MS')"
        scalar("datetime-"+suffix,7,f"CONVERT(varchar(23),CAST('{date}' AS datetime),121)",p,
               f"to_char(timestamp '{date}','YYYY-MM-DD HH24:MI:SS.MS')","Kept microseconds instead of the datetime grid.")
    scalar("datediff-day",8,"DATEDIFF(day,'20261001 23:59:59','20261002 00:00:00')",
           "date '2026-10-02'-date '2026-10-01'",
           "floor(extract(epoch FROM timestamp '2026-10-02'-timestamp '2026-10-01 23:59:59')/86400)","Counted elapsed full days.")
    scalar("datediff-year",8,"DATEDIFF(year,'20251231','20260101')","2026-2025",
           "extract(year FROM age(date '2026-01-01',date '2025-12-31'))","Counted elapsed full years.")
    scalar("datefirst",9,"DATEPART(weekday,CAST('20261004' AS date))",
           "extract(isodow FROM date '2026-10-04')","extract(dow FROM date '2026-10-04')","Ignored DATEFIRST=1.",pre="SET DATEFIRST 1;")
    scalar("dateformat",9,"CONVERT(varchar(10),CAST('03/04/2026' AS date),23)",
           "to_char(to_date('03/04/2026','DD/MM/YYYY'),'YYYY-MM-DD')",
           "to_char(to_date('03/04/2026','MM/DD/YYYY'),'YYYY-MM-DD')","Read day/month as month/day.",pre="SET DATEFORMAT dmy;")
    scalar("convert-style",9,"CONVERT(varchar(10),CAST('20260403' AS date),103)",
           "to_char(date '2026-04-03','DD/MM/YYYY')","to_char(date '2026-04-03','MM/DD/YYYY')","Changed style103 date order.")
    scalar("round-negative",10,"ROUND(CAST(-150 AS decimal(6,0)),-2)","round(-150::numeric,-2)","trunc(-150::numeric,-2)","Truncated instead of rounding.")
    scalar("money-scale",10,"CONVERT(varchar(30),CAST(1.23456 AS money),2)",
           "round(1.23456::numeric,4)","1.23456::numeric","Kept fifth money decimal.")
    catch_source=sp("INSERT dbo.effects VALUES(1,10); BEGIN TRY DECLARE @zero int=0; SELECT 1/@zero; END TRY BEGIN CATCH INSERT dbo.effects VALUES(2,20); END CATCH; SELECT CONVERT(varchar(20),COUNT(*)) AS value FROM dbo.effects;")
    # Use assignment to avoid adding a result-set shape before SQL Server's caught error.
    catch_source=catch_source.replace("SELECT 1/@zero;","DECLARE @unused int; SET @unused=1/@zero;")
    catch_correct=fn("INSERT INTO dbo.effects VALUES(1,10); BEGIN PERFORM 1/0; EXCEPTION WHEN division_by_zero THEN INSERT INTO dbo.effects VALUES(2,20); END; RETURN QUERY SELECT count(*)::text FROM dbo.effects;")
    catch_wrong=fn("BEGIN INSERT INTO dbo.effects VALUES(1,10); PERFORM 1/0; EXCEPTION WHEN division_by_zero THEN INSERT INTO dbo.effects VALUES(2,20); END; RETURN QUERY SELECT count(*)::text FROM dbo.effects;")
    add("catch-retains-prior-work",11,catch_source,catch_correct,catch_wrong,"Moved prior write into PG exception subtransaction.")
    xact=sp("SET XACT_ABORT ON; BEGIN TRY BEGIN TRAN; INSERT dbo.effects VALUES(1,10); DECLARE @zero int=0,@unused int; SET @unused=1/@zero; COMMIT; END TRY BEGIN CATCH IF @@TRANCOUNT>0 ROLLBACK; END CATCH; SELECT CONVERT(varchar(20),COUNT(*)) AS value FROM dbo.effects;")
    xgood=fn("BEGIN INSERT INTO dbo.effects VALUES(1,10); PERFORM 1/0; EXCEPTION WHEN division_by_zero THEN NULL; END; RETURN QUERY SELECT count(*)::text FROM dbo.effects;")
    xbad=fn("INSERT INTO dbo.effects VALUES(1,10); BEGIN PERFORM 1/0; EXCEPTION WHEN division_by_zero THEN NULL; END; RETURN QUERY SELECT count(*)::text FROM dbo.effects;")
    add("xact-abort",12,xact,xgood,xbad,"Failed to roll back the write in the aborted transaction.")
    nested=sp("BEGIN TRAN; INSERT dbo.effects VALUES(1,10); BEGIN TRAN; INSERT dbo.effects VALUES(2,20); COMMIT; ROLLBACK; SELECT CONVERT(varchar(20),COUNT(*)) AS value FROM dbo.effects;")
    ngood=fn("BEGIN INSERT INTO dbo.effects VALUES(1,10); BEGIN INSERT INTO dbo.effects VALUES(2,20); END; RAISE EXCEPTION 'outer rollback' USING ERRCODE='P0001'; EXCEPTION WHEN SQLSTATE 'P0001' THEN NULL; END; RETURN QUERY SELECT count(*)::text FROM dbo.effects;")
    nbad=fn("INSERT INTO dbo.effects VALUES(2,20); BEGIN INSERT INTO dbo.effects VALUES(1,10); RAISE EXCEPTION 'outer rollback' USING ERRCODE='P0001'; EXCEPTION WHEN SQLSTATE 'P0001' THEN NULL; END; RETURN QUERY SELECT count(*)::text FROM dbo.effects;")
    add("nested-transaction-rollback",12,nested,ngood,nbad,"Committed inner work independently of the outer rollback.")
    add("informational-raiserror",13,sp("RAISERROR('public informational message',10,1); SELECT 'done' AS value;"),
        fn("RAISE NOTICE 'public informational message'; RETURN QUERY SELECT 'done'::text;"),
        fn("RAISE EXCEPTION 'public informational message'; RETURN QUERY SELECT 'done'::text;"),
        "Raised an error for informational severity10.")
    ids="CREATE TABLE dbo.items(id int IDENTITY(1,1) PRIMARY KEY,v int);\nCREATE TABLE dbo.audit(id int IDENTITY(100,1) PRIMARY KEY,v int);\nGO\nCREATE TRIGGER dbo.items_audit ON dbo.items AFTER INSERT AS BEGIN SET NOCOUNT ON; INSERT dbo.audit(v) SELECT v FROM inserted; END;\nGO\n"
    idp="CREATE TABLE dbo.items(id integer GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,v integer);\nCREATE TABLE dbo.audit(id integer GENERATED BY DEFAULT AS IDENTITY(START WITH 100) PRIMARY KEY,v integer);\nCREATE FUNCTION dbo.items_audit() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN INSERT INTO dbo.audit(v) VALUES(NEW.v); RETURN NEW; END; $$;\nCREATE TRIGGER items_audit AFTER INSERT ON dbo.items FOR EACH ROW EXECUTE FUNCTION dbo.items_audit();\n"
    add("scope-identity-trigger",14,sp("INSERT dbo.items(v) VALUES(7); SELECT CONVERT(varchar(20),CONVERT(int,SCOPE_IDENTITY())) AS value;"),
        fn("INSERT INTO dbo.items(v) VALUES(7) RETURNING id INTO saved; RETURN QUERY SELECT saved::text;","saved integer;"),
        fn("INSERT INTO dbo.items(v) VALUES(7); RETURN QUERY SELECT lastval()::text;"),
        "Read trigger identity instead of call-scope identity.",ss=ids,ps=idp)
    gap_source=sp("BEGIN TRAN; INSERT dbo.items(v) VALUES(1); ROLLBACK; INSERT dbo.items(v) VALUES(2); SELECT CONVERT(varchar(20),CONVERT(int,SCOPE_IDENTITY())) AS value;")
    gap_body="BEGIN INSERT INTO dbo.items(v) VALUES(1); RAISE EXCEPTION 'rollback'; EXCEPTION WHEN SQLSTATE 'P0001' THEN NULL; END; "
    add("identity-rollback-gap",14,gap_source,
        fn(gap_body+"INSERT INTO dbo.items(v) VALUES(2) RETURNING id INTO saved; RETURN QUERY SELECT saved::text;","saved integer;"),
        fn(gap_body+"ALTER SEQUENCE dbo.items_id_seq RESTART WITH 1; INSERT INTO dbo.items(v) VALUES(2) RETURNING id INTO saved; RETURN QUERY SELECT saved::text;","saved integer;"),
        "Rewound identity after rollback.",ss="CREATE TABLE dbo.items(id int IDENTITY(1,1) PRIMARY KEY,v int);\nGO\n",
        ps="CREATE TABLE dbo.items(id integer GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,v integer);\n")
    add("rowcount-lifetime",15,sp("DECLARE @n int; INSERT dbo.effects VALUES(1,10),(2,20); SET @n=@@ROWCOUNT; SELECT CONVERT(varchar(20),@n) AS value;"),
        fn("INSERT INTO dbo.effects VALUES(1,10),(2,20); GET DIAGNOSTICS n=ROW_COUNT; RETURN QUERY SELECT n::text;","n integer;"),
        fn("INSERT INTO dbo.effects VALUES(1,10),(2,20); PERFORM 1; GET DIAGNOSTICS n=ROW_COUNT; RETURN QUERY SELECT n::text;","n integer;"),
        "Read row count after a different statement.")
    multi="CREATE OR REPLACE PROCEDURE dbo.trap(INOUT first_set refcursor,INOUT second_set refcursor) LANGUAGE plpgsql AS $$ BEGIN OPEN first_set FOR SELECT 'first'::text AS value; OPEN second_set FOR SELECT 'second'::text AS value; END; $$;\n"
    add("multiple-result-sets",16,sp("SELECT 'first' AS value; SELECT 'second' AS value;"),multi,
        multi.replace("'second'::text","'first'::text"),"Duplicated the first result in the second cursor.",
        convention={"source":"EXEC dbo.trap","target":"CALL dbo.trap('first_set','second_set')",
                    "refcursor_order":["first_set","second_set"],"caller_transaction":"BEGIN/CALL/FETCH/FETCH/COMMIT explicitly declared; no cleanup rollback",
                    "target_return_code":"mapped-default-zero","output_cursor_handles":"not business OUTPUT parameters"})
    outpg="CREATE OR REPLACE PROCEDURE dbo.trap(INOUT answer integer) LANGUAGE plpgsql AS $$ BEGIN answer:=7; END; $$;\n"
    add("output-parameter",17,sp("SET @answer=7;","@answer int OUTPUT"),outpg,outpg.replace(":=7",":=8"),
        "Changed OUTPUT value.",parameters={"answer":None},
        convention={"source":"EXEC dbo.trap @answer OUTPUT","target":"CALL dbo.trap(NULL)","output_mapping":{"answer":"answer"},"target_return_code":"mapped-default-zero"})
    retpg="CREATE OR REPLACE PROCEDURE dbo.trap(INOUT return_code integer) LANGUAGE plpgsql AS $$ BEGIN return_code:=0; END; $$;\n"
    add("default-return-code",17,sp("DECLARE @n int=1;"),retpg,retpg.replace(":=0",":=1"),
        "Changed implicit return0 to1.",convention={"source":"EXEC @return_code=dbo.trap","target":"CALL dbo.trap(NULL)","return_mapping":"return_code"})
    up_setup="CREATE TABLE dbo.matches(k int,v int); INSERT dbo.matches VALUES(1,10),(1,20); INSERT dbo.effects VALUES(1,0);\nGO\n"
    upp_setup="CREATE TABLE dbo.matches(k integer,v integer); INSERT INTO dbo.matches VALUES(1,10),(1,20); INSERT INTO dbo.effects VALUES(1,0);\n"
    add("update-from-ambiguous",18,sp("UPDATE e SET amount=m.v FROM dbo.effects e JOIN dbo.matches m ON e.id=m.k; SELECT CONVERT(varchar(20),amount) AS value FROM dbo.effects;"),
        fn("UPDATE dbo.effects e SET amount=m.v FROM dbo.matches m WHERE e.id=m.k; RETURN QUERY SELECT amount::text FROM dbo.effects;"),
        fn("UPDATE dbo.effects e SET amount=(SELECT sum(m.v) FROM dbo.matches m WHERE e.id=m.k); RETURN QUERY SELECT amount::text FROM dbo.effects;"),
        "Aggregated duplicate matches; correct mapping itself remains policy-gated.",ss=up_setup,ps=upp_setup)
    merge_source=sp("MERGE dbo.effects AS t USING (VALUES(1,20),(2,30)) AS s(id,amount) ON t.id=s.id WHEN MATCHED THEN UPDATE SET amount=s.amount WHEN NOT MATCHED THEN INSERT(id,amount) VALUES(s.id,s.amount); SELECT CONVERT(varchar(20),SUM(amount)) AS value FROM dbo.effects;")
    merge_target=fn("MERGE INTO dbo.effects AS t USING (VALUES(1,20),(2,30)) AS s(id,amount) ON t.id=s.id WHEN MATCHED THEN UPDATE SET amount=s.amount WHEN NOT MATCHED THEN INSERT(id,amount) VALUES(s.id,s.amount); RETURN QUERY SELECT sum(amount)::text FROM dbo.effects;")
    add("merge-upsert",19,merge_source,merge_target,merge_target.replace("amount=s.amount","amount=t.amount"),
        "Ignored matched update.",ss="INSERT dbo.effects VALUES(1,10);\nGO\n",ps="INSERT INTO dbo.effects VALUES(1,10);\n")
    tempgood=fn("CREATE TEMP TABLE scratch(n integer); INSERT INTO scratch VALUES(1); RETURN QUERY SELECT count(*)::text FROM scratch; DROP TABLE scratch;")
    add("temp-table-scope",20,sp("CREATE TABLE #scratch(n int); INSERT #scratch VALUES(1); SELECT CONVERT(varchar(20),COUNT(*)) AS value FROM #scratch;"),
        tempgood,tempgood.replace(" DROP TABLE scratch;",""),"Leaked a session temp table.")
    add("table-variable-scope",20,sp("DECLARE @scratch TABLE(n int); INSERT @scratch VALUES(1); SELECT CONVERT(varchar(20),COUNT(*)) AS value FROM @scratch;"),
        fn("RETURN QUERY SELECT cardinality(ARRAY[1])::text;"),
        fn("CREATE TEMP TABLE scratch(n integer); INSERT INTO scratch VALUES(1); RETURN QUERY SELECT count(*)::text FROM scratch;"),
        "Replaced local table variable with a leaking temp table.")
    dyn=sp("DECLARE @out nvarchar(100); EXEC sp_executesql N'SELECT @r=@p',N'@p nvarchar(100),@r nvarchar(100) OUTPUT',@p=N'O''Brien',@r=@out OUTPUT; SELECT @out AS value;")
    add("dynamic-parameter-binding",21,dyn,
        fn("EXECUTE 'SELECT $1::text' INTO saved USING 'O''Brien'; RETURN QUERY SELECT saved;","saved text;"),
        fn("EXECUTE 'SELECT ''O' || chr(39) || 'Brien''' INTO saved; RETURN QUERY SELECT saved;","saved text;"),
        "Concatenated a quoted value rather than binding it.")
    curs=sp("DECLARE @n int,@total int=0; DECLARE c CURSOR LOCAL FAST_FORWARD FOR SELECT v FROM (VALUES(1),(2),(3)) x(v) ORDER BY v; OPEN c; FETCH NEXT FROM c INTO @n; WHILE @@FETCH_STATUS=0 BEGIN SET @total=@total+@n; FETCH NEXT FROM c INTO @n; END; CLOSE c; DEALLOCATE c; SELECT CONVERT(varchar(20),@total) AS value;")
    cp=fn("FOR n IN SELECT v FROM (VALUES(1),(2),(3)) x(v) ORDER BY v LOOP total:=total+n; END LOOP; RETURN QUERY SELECT total::text;","n integer; total integer:=0;")
    add("cursor-fetch-status",22,curs,cp,cp.replace("total:=total+n;","EXIT WHEN n=3; total:=total+n;"),"Dropped the last fetched row.")
    trigs="CREATE TABLE dbo.audit(total int);\nGO\nCREATE TRIGGER dbo.effects_audit ON dbo.effects AFTER INSERT AS BEGIN SET NOCOUNT ON; INSERT dbo.audit(total) SELECT SUM(amount) FROM inserted; END;\nGO\n"
    trigp="CREATE TABLE dbo.audit(total integer); CREATE FUNCTION dbo.effects_audit() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN INSERT INTO dbo.audit(total) SELECT sum(amount) FROM newrows; RETURN NULL; END; $$; CREATE TRIGGER effects_audit AFTER INSERT ON dbo.effects REFERENCING NEW TABLE AS newrows FOR EACH STATEMENT EXECUTE FUNCTION dbo.effects_audit();\n"
    trigw="CREATE TABLE dbo.audit(total integer); CREATE FUNCTION dbo.effects_audit() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN INSERT INTO dbo.audit(total) VALUES(NEW.amount); RETURN NEW; END; $$; CREATE TRIGGER effects_audit AFTER INSERT ON dbo.effects FOR EACH ROW EXECUTE FUNCTION dbo.effects_audit();\n"
    trigt=fn("INSERT INTO dbo.effects VALUES(1,10),(2,20); RETURN QUERY SELECT count(*)::text FROM dbo.audit;")
    add("set-trigger",23,sp("INSERT dbo.effects VALUES(1,10),(2,20); SELECT CONVERT(varchar(20),COUNT(*)) AS value FROM dbo.audit;"),trigt,trigt,
        "Used per-row trigger instead of a statement transition table.",ss=trigs,ps=trigp,ws=trigw)
    scalar("bit",24,"CAST(2 AS bit)","CASE WHEN 2<>0 THEN 1 ELSE 0 END","CASE WHEN 2=1 THEN 1 ELSE 0 END","Mapped only1 to true.")
    scalar("uuid-case",24,"LOWER(CONVERT(varchar(36),CAST('A0B1C2D3-E4F5-4678-9012-123456789ABC' AS uniqueidentifier)))",
           "lower('A0B1C2D3-E4F5-4678-9012-123456789ABC'::uuid::text)",
           "upper('A0B1C2D3-E4F5-4678-9012-123456789ABC'::uuid::text)","Changed declared lowercase UUID text mapping.")
    scalar("unordered-top",25,"SELECT TOP(1) v FROM (VALUES(1),(2)) x(v)",
           "SELECT v FROM (VALUES(1),(2)) x(v) LIMIT 1",
           "SELECT v FROM (VALUES(1),(2)) x(v) ORDER BY v DESC LIMIT 1",
           "Introduced descending order; all variants require policy, never coincidental equivalence.")
    # Prospective return-contract correction. The original r5 assets/evidence
    # remain in their retained bundles. Status is produced by the twin's actual
    # exception path, never supplied as a constant by the adapter/comparator.
    for row in rows:
        if row['id'] in ('nested-transaction-rollback','identity-rollback-gap'):
            # Semantically inert, but actually executed and visible to the native
            # profiler. Preserve the former NULL-handler sources in prior runs.
            for variant in ('correct_sql','wrong_sql'):
                row[variant]=row[variant].replace("THEN NULL;", "THEN PERFORM 1;")
        if row['id'] not in ('ci-unique','catch-retains-prior-work','xact-abort'):
            continue
        row['calling_convention'] = dict(row['calling_convention'],
            result_return_mapping={'column':'tsql_return_code','type':'integer'},
            target_return_code='actual-return-column-from-twin-exception-path')
        number = -4 if row['id']=='ci-unique' else -6
        handler = 'unique_violation' if number==-4 else 'division_by_zero'
        for variant in ('correct_sql','wrong_sql'):
            sql=row[variant].replace('RETURNS TABLE(value text)',
                'RETURNS TABLE(value text, tsql_return_code integer)')
            sql=sql.replace('AS $trap$\nBEGIN','AS $trap$\nDECLARE mapped_status integer:=0;\nBEGIN')
            sql=sql.replace('EXCEPTION WHEN '+handler+' THEN',
                'EXCEPTION WHEN '+handler+' THEN mapped_status:='+str(number)+';')
            sql=sql.replace('RETURN QUERY SELECT count(*)::text FROM dbo.',
                'RETURN QUERY SELECT count(*)::text, mapped_status FROM dbo.')
            row[variant]=sql
        if row['id']=='xact-abort':
            for variant in ('correct_sql','wrong_sql'):
                row[variant]=row[variant].replace('INSERT INTO dbo.effects VALUES(1,10);',
                    'INSERT INTO dbo.effects VALUES(1,10); mapped_status:=-6;').replace(
                    'THEN mapped_status:=-6; NULL;', 'THEN PERFORM 1;')
        if row['id']=='ci-unique':
            # SQL Server commits the first insert before the caught second insert.
            # A PostgreSQL function would roll it back on an unhandled exception;
            # a top-level procedure preserves that public partial-commit contract.
            for variant in ('correct_sql','wrong_sql'):
                sql=row[variant].replace('FUNCTION dbo.trap() RETURNS TABLE(value text, tsql_return_code integer)',
                    'PROCEDURE dbo.trap(OUT value text, OUT tsql_return_code integer)')
                sql=sql.replace("INSERT INTO dbo.names(v) VALUES ('A');", "INSERT INTO dbo.names(v) VALUES ('A'); COMMIT;")
                sql=sql.replace('RETURN QUERY SELECT count(*)::text, mapped_status FROM dbo.names;',
                    'SELECT count(*)::text, mapped_status INTO value, tsql_return_code FROM dbo.names;')
                row[variant]=sql
            row['calling_convention']=dict(row['calling_convention'],target='CALL dbo.trap(NULL,NULL)',
                transaction_contract='top-level procedure commits the first insert before the second statement')
    return rows


def artifacts(root: Path) -> dict[str,bytes]:
    outputs={}
    rows=corpus()
    if len(rows)!=42 or {r["trap_family"] for r in rows}!=set(range(1,26)):
        raise ValueError("trap-family-or-case-closure")
    public=[]
    for row in rows:
        record={k:v for k,v in row.items() if not k.endswith("_sql") and not k.endswith("_setup")}
        assets={}
        for role,key in (("source","source_sql"),("correct","correct_sql"),("wrong","wrong_sql"),
                         ("source-setup","source_setup"),("target-setup","target_setup"),("wrong-setup","wrong_setup")):
            name=ROOT_DIR+"/corpus/"+row["id"]+"/"+role+".sql"
            raw=("-- Authored public M0 trap; NOT natively qualified.\n"+row[key]).encode()
            outputs[name]=raw
            assets[role]={"path":name,"sha256":hashlib.sha256(raw).hexdigest()}
        if outputs[assets["correct"]["path"]]==outputs[assets["wrong"]["path"]] and outputs[assets["target-setup"]["path"]]==outputs[assets["wrong-setup"]["path"]]:
            raise ValueError("mutant-has-no-changed-bytes")
        record["assets"]=assets
        record['coverage_scenarios']=[]
        if row['id'] in ('ci-unique','xact-abort'):
            scenario='unexpected-check' if row['id']=='ci-unique' else 'trigger-rollback'
            if row['id']=='ci-unique':
                extra_source="ALTER TABLE dbo.names ADD CONSTRAINT names_upper CHECK(v COLLATE Latin1_General_100_BIN2 <> 'a');\nGO\n"
                extra_target="ALTER TABLE dbo.names ADD CONSTRAINT names_upper CHECK(v <> 'a');\n"
                convention=dict(record['calling_convention'],public_error_equivalence='check-constraint-547-23514')
            else:
                extra_source="CREATE TRIGGER dbo.rollback_probe ON dbo.effects AFTER INSERT AS BEGIN SET NOCOUNT ON; ROLLBACK TRANSACTION; DECLARE @zero int=0,@unused int; SET @unused=1/@zero; END;\nGO\n"
                extra_target="CREATE FUNCTION dbo.rollback_probe() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'public rollback coverage case' USING ERRCODE='22012'; END; $$; CREATE TRIGGER rollback_probe BEFORE INSERT ON dbo.effects FOR EACH ROW EXECUTE FUNCTION dbo.rollback_probe();\n"
                convention=dict(record['calling_convention'])
            scenario_assets=dict(assets)
            for role,key,extra in [('source-setup','source_setup',extra_source),('target-setup','target_setup',extra_target),('wrong-setup','wrong_setup',extra_target)]:
                name=ROOT_DIR+'/corpus/'+row['id']+'/'+scenario+'-'+role+'.sql'
                setup=row[key]
                if row['id']=='ci-unique' and role=='source-setup':
                    setup=setup.replace('Latin1_General_100_CI_AS','Latin1_General_100_BIN2')
                raw=(setup+extra).encode();outputs[name]=raw
                scenario_assets[role]={'path':name,'sha256':hashlib.sha256(raw).hexdigest()}
            record['coverage_scenarios'].append({'id':scenario,'assets':scenario_assets,'calling_convention':convention})
        public.append(record)
    manifest=seal({"schema":"tsql-trap-corpus/1","public_fixture":True,"authored_original":True,
                   "case_count":len(rows),"family_count":25,"procedures":public,"native_pairs_run":0,
                   "correct_twins_qualified":0,"wrong_twins_killed":0,"signed_native_receipts":0,
                   "coverage_source":None,"coverage_target":None,
                   "acceptance":"unassessed; expected labels are not observations"})
    outputs[ROOT_DIR+"/corpus.json"]=canonical_bytes(manifest)+b"\n"
    outputs[ROOT_DIR+"/compatibility-ledger.json"]=canonical_bytes(build_ledger(root))+b"\n"
    return outputs


def write_artifacts(root: Path):
    for name,raw in artifacts(root).items():
        path=root/name
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(raw)


if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser(description="Write authored offline public fixtures; never execute SQL.")
    p.add_argument("--root",type=Path,required=True)
    args=p.parse_args();write_artifacts(args.root)
