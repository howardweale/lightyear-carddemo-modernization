-- Authored public M0 trap; NOT natively qualified.
CREATE OR REPLACE FUNCTION dbo.trap_convert_style(day_value date) RETURNS TABLE(value text) LANGUAGE plpgsql AS $trap$
BEGIN
 RETURN QUERY SELECT (to_char(day_value,'MM/DD/YYYY'))::text;
END;
$trap$;
