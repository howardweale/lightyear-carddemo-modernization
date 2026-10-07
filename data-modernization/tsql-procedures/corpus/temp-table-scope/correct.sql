-- Authored public M0 trap; NOT natively qualified.
CREATE OR REPLACE FUNCTION dbo.trap() RETURNS TABLE(value text) LANGUAGE plpgsql AS $trap$
BEGIN
 CREATE TEMP TABLE scratch(n integer); INSERT INTO scratch VALUES(1); RETURN QUERY SELECT count(*)::text FROM scratch; DROP TABLE scratch;
END;
$trap$;
