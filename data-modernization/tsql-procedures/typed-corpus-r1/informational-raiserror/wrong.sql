-- Authored public M0 trap; NOT natively qualified.
CREATE OR REPLACE FUNCTION dbo.trap_informational_raiserror(input_value text) RETURNS TABLE(value text) LANGUAGE plpgsql AS $trap$
BEGIN
 RAISE EXCEPTION '%', input_value; RETURN QUERY SELECT 'done'::text;
END;
$trap$;
