-- Authored public M0 trap; NOT natively qualified.
CREATE OR REPLACE FUNCTION dbo.trap() RETURNS TABLE(value text) LANGUAGE plpgsql AS $trap$
BEGIN
 RAISE NOTICE 'public informational message'; RETURN QUERY SELECT 'done'::text;
END;
$trap$;
