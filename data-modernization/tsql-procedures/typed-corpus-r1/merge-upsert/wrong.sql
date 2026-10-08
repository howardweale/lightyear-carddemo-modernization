-- Authored public M0 trap; NOT natively qualified.
CREATE OR REPLACE FUNCTION dbo.trap_merge_upsert(arg_amount integer) RETURNS TABLE(value text) LANGUAGE plpgsql AS $trap$
BEGIN
 MERGE INTO dbo.effects AS t USING (VALUES(1,arg_amount),(2,30)) AS s(id,amount) ON t.id=s.id WHEN MATCHED THEN UPDATE SET amount=t.amount WHEN NOT MATCHED THEN INSERT(id,amount) VALUES(s.id,s.amount); RETURN QUERY SELECT sum(amount)::text FROM dbo.effects;
END;
$trap$;
