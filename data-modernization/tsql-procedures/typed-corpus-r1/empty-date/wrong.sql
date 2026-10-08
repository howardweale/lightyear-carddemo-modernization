-- Authored public M0 trap; NOT natively qualified.
CREATE OR REPLACE FUNCTION dbo.trap_empty_date(input_value text) RETURNS TABLE(value text) LANGUAGE plpgsql AS $trap$
BEGIN
 RETURN QUERY SELECT (to_char(nullif(input_value,input_value)::timestamp,'YYYY-MM-DD'))::text;
END;
$trap$;
