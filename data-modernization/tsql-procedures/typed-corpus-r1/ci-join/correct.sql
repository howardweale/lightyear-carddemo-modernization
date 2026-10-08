-- Authored public M0 trap; NOT natively qualified.
CREATE OR REPLACE FUNCTION dbo.trap_ci_join(input_value text) RETURNS TABLE(value text) LANGUAGE plpgsql AS $trap$
BEGIN
 RETURN QUERY SELECT (SELECT count(*) FROM (VALUES (input_value),('a')) a(v) JOIN (VALUES (input_value)) b(v) ON lower(a.v)=lower(b.v))::text;
END;
$trap$;
