-- Authored public M0 trap; NOT natively qualified.
CREATE OR REPLACE FUNCTION dbo.trap_scope_identity_trigger(input_value integer) RETURNS TABLE(value text) LANGUAGE plpgsql AS $trap$
BEGIN
 INSERT INTO dbo.items(v) VALUES(input_value); RETURN QUERY SELECT lastval()::text;
END;
$trap$;
