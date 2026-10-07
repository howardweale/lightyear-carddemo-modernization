-- Authored public M0 trap; NOT natively qualified.
CREATE OR REPLACE FUNCTION dbo.trap() RETURNS TABLE(value text) LANGUAGE plpgsql AS $trap$
BEGIN
 RETURN QUERY SELECT (SELECT count(*) FROM (VALUES ('A'),('a')) a(v) JOIN (VALUES ('A')) b(v) ON lower(a.v)=lower(b.v))::text;
END;
$trap$;
