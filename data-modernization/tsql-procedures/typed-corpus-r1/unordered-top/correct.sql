-- Authored public M0 trap; NOT natively qualified.
CREATE OR REPLACE FUNCTION dbo.trap_unordered_top(input_value integer) RETURNS TABLE(value text) LANGUAGE plpgsql AS $trap$
BEGIN
 RETURN QUERY SELECT (SELECT v FROM (VALUES(1),(input_value)) x(v) LIMIT 1)::text;
END;
$trap$;
