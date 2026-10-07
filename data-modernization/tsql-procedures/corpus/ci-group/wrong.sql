-- Authored public M0 trap; NOT natively qualified.
CREATE OR REPLACE FUNCTION dbo.trap() RETURNS TABLE(value text) LANGUAGE plpgsql AS $trap$
BEGIN
 RETURN QUERY SELECT (SELECT count(*) FROM (SELECT v FROM (VALUES ('A'),('a')) x(v) GROUP BY v) g)::text;
END;
$trap$;
