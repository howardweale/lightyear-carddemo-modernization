-- Authored public M0 trap; NOT natively qualified.
CREATE OR REPLACE FUNCTION dbo.trap() RETURNS TABLE(value text) LANGUAGE plpgsql AS $trap$
BEGIN
 INSERT INTO dbo.effects VALUES(2,20); BEGIN INSERT INTO dbo.effects VALUES(1,10); RAISE EXCEPTION 'outer rollback' USING ERRCODE='P0001'; EXCEPTION WHEN SQLSTATE 'P0001' THEN NULL; END; RETURN QUERY SELECT count(*)::text FROM dbo.effects;
END;
$trap$;
