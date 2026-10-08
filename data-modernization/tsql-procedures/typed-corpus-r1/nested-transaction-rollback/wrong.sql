-- Authored public M0 trap; NOT natively qualified.
CREATE OR REPLACE FUNCTION dbo.trap_nested_transaction_rollback(arg_amount integer) RETURNS TABLE(value text) LANGUAGE plpgsql AS $trap$
BEGIN
 INSERT INTO dbo.effects VALUES(2,20); BEGIN INSERT INTO dbo.effects VALUES(1,arg_amount); RAISE EXCEPTION 'outer rollback' USING ERRCODE='P0001'; EXCEPTION WHEN SQLSTATE 'P0001' THEN PERFORM 1; END; RETURN QUERY SELECT count(*)::text FROM dbo.effects;
END;
$trap$;
