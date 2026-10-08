-- Authored public M0 trap; NOT natively qualified.
CREATE OR REPLACE FUNCTION dbo.trap_scope_identity_trigger(input_value integer) RETURNS TABLE(value text) LANGUAGE plpgsql AS $trap$
DECLARE saved integer;
BEGIN
 INSERT INTO dbo.items(v) VALUES(input_value) RETURNING id INTO saved; RETURN QUERY SELECT saved::text;
END;
$trap$;
