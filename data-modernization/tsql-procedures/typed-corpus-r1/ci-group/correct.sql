-- Authored public M0 trap; NOT natively qualified.
CREATE OR REPLACE FUNCTION dbo.trap_ci_group(input_value text) RETURNS TABLE(value text) LANGUAGE plpgsql AS $trap$
BEGIN
 RETURN QUERY SELECT (SELECT count(*) FROM (SELECT lower(v) FROM (VALUES (input_value),('a')) x(v) GROUP BY lower(v)) g)::text;
END;
$trap$;
