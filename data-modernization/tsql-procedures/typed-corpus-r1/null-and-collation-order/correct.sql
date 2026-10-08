-- Authored public M0 trap; NOT natively qualified.
CREATE OR REPLACE FUNCTION dbo.trap_null_and_collation_order(input_value text) RETURNS TABLE(value text) LANGUAGE plpgsql AS $trap$
BEGIN
 RETURN QUERY SELECT v FROM (VALUES (NULL::text),('a'),(input_value)) t(v) ORDER BY lower(v) COLLATE "C" NULLS FIRST;
END;
$trap$;
