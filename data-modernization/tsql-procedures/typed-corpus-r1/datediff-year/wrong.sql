-- Authored public M0 trap; NOT natively qualified.
CREATE OR REPLACE FUNCTION dbo.trap_datediff_year(finish timestamp) RETURNS TABLE(value text) LANGUAGE plpgsql AS $trap$
BEGIN
 RETURN QUERY SELECT (extract(year FROM age(finish::date,date '2025-12-31')))::text;
END;
$trap$;
