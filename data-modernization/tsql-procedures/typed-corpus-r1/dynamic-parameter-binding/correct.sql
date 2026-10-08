-- Authored public M0 trap; NOT natively qualified.
CREATE OR REPLACE FUNCTION dbo.trap_dynamic_parameter_binding(input_value text) RETURNS TABLE(value text) LANGUAGE plpgsql AS $trap$
DECLARE saved text;
BEGIN
 EXECUTE 'SELECT $1::text' INTO saved USING input_value; RETURN QUERY SELECT saved;
END;
$trap$;
