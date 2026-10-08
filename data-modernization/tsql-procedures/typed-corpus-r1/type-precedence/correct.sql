-- Authored public M0 trap; NOT natively qualified.
CREATE OR REPLACE FUNCTION dbo.trap_type_precedence(input_value text) RETURNS TABLE(value text) LANGUAGE plpgsql AS $trap$
BEGIN
 RETURN QUERY SELECT (CAST(input_value AS integer)+3)::text;
END;
$trap$;
