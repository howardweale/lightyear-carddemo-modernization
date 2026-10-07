-- Authored public M0 trap; NOT natively qualified.
CREATE OR REPLACE FUNCTION dbo.trap() RETURNS TABLE(value text) LANGUAGE plpgsql AS $trap$
BEGIN
 RETURN QUERY SELECT (to_char(timestamp '2026-10-01 00:00:00.001','YYYY-MM-DD HH24:MI:SS.MS'))::text;
END;
$trap$;
