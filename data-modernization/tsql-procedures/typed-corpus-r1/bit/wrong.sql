-- Authored public M0 trap; NOT natively qualified.
CREATE OR REPLACE FUNCTION dbo.trap_bit(input_value integer) RETURNS TABLE(value text) LANGUAGE plpgsql AS $trap$
BEGIN
 RETURN QUERY SELECT (CASE WHEN input_value=1 THEN 1 ELSE 0 END)::text;
END;
$trap$;
