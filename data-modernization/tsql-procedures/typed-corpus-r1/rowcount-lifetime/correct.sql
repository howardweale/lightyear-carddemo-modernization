-- Authored public M0 trap; NOT natively qualified.
CREATE OR REPLACE FUNCTION dbo.trap_rowcount_lifetime(arg_amount integer) RETURNS TABLE(value text) LANGUAGE plpgsql AS $trap$
DECLARE n integer;
BEGIN
 INSERT INTO dbo.effects VALUES(1,arg_amount),(2,20); GET DIAGNOSTICS n=ROW_COUNT; RETURN QUERY SELECT n::text;
END;
$trap$;
