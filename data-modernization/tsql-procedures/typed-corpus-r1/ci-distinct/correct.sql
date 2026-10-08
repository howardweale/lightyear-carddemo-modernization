-- Authored public M0 trap; NOT natively qualified.
CREATE OR REPLACE FUNCTION dbo.trap_ci_distinct(input_value text) RETURNS TABLE(value text) LANGUAGE plpgsql AS $trap$
BEGIN
 RETURN QUERY SELECT (SELECT count(DISTINCT lower(v)) FROM (VALUES (input_value),('a')) x(v))::text;
END;
$trap$;
