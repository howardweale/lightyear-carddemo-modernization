-- Authored public M0 trap; NOT natively qualified.
CREATE OR REPLACE FUNCTION dbo.trap_trailing_char(input_value text) RETURNS TABLE(value text) LANGUAGE plpgsql AS $trap$
BEGIN
 RETURN QUERY SELECT (CASE WHEN input_value='A' THEN 1 ELSE 0 END)::text;
END;
$trap$;
