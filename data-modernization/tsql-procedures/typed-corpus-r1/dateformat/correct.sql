-- Authored public M0 trap; NOT natively qualified.
CREATE OR REPLACE FUNCTION dbo.trap_dateformat(input_value text) RETURNS TABLE(value text) LANGUAGE plpgsql AS $trap$
BEGIN
 RETURN QUERY SELECT (to_char(to_date(input_value,'DD/MM/YYYY'),'YYYY-MM-DD'))::text;
END;
$trap$;
