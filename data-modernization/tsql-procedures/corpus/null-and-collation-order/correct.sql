-- Authored public M0 trap; NOT natively qualified.
CREATE OR REPLACE FUNCTION dbo.trap() RETURNS TABLE(value text) LANGUAGE plpgsql AS $trap$
BEGIN
 RETURN QUERY SELECT v FROM (VALUES (NULL::text),('a'),('B')) t(v) ORDER BY lower(v) COLLATE "C" NULLS FIRST;
END;
$trap$;
