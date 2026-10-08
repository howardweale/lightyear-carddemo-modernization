-- Authored public M0 trap; NOT natively qualified.
CREATE OR REPLACE FUNCTION dbo.trap_set_trigger(arg_amount integer) RETURNS TABLE(value text) LANGUAGE plpgsql AS $trap$
BEGIN
 INSERT INTO dbo.effects VALUES(1,arg_amount),(2,20); RETURN QUERY SELECT count(*)::text FROM dbo.audit;
END;
$trap$;
