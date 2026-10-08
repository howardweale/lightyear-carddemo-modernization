-- Authored public M0 trap; NOT natively qualified.
CREATE OR REPLACE FUNCTION dbo.trap_datefirst(day_value date) RETURNS TABLE(value text) LANGUAGE plpgsql AS $trap$
BEGIN
 RETURN QUERY SELECT (extract(dow FROM day_value))::text;
END;
$trap$;
