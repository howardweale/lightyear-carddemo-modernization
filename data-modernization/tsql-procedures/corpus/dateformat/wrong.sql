-- Authored public M0 trap; NOT natively qualified.
CREATE OR REPLACE FUNCTION dbo.trap() RETURNS TABLE(value text) LANGUAGE plpgsql AS $trap$
BEGIN
 RETURN QUERY SELECT (to_char(to_date('03/04/2026','MM/DD/YYYY'),'YYYY-MM-DD'))::text;
END;
$trap$;
