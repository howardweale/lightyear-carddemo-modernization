-- Authored public M0 trap; NOT natively qualified.
CREATE OR REPLACE FUNCTION dbo.trap() RETURNS TABLE(value text) LANGUAGE plpgsql AS $trap$
BEGIN
 RETURN QUERY SELECT (floor(extract(epoch FROM timestamp '2026-10-02'-timestamp '2026-10-01 23:59:59')/86400))::text;
END;
$trap$;
