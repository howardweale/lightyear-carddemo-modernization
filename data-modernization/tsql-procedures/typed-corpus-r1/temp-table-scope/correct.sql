-- Authored public M0 trap; NOT natively qualified.
CREATE OR REPLACE FUNCTION dbo.trap_temp_table_scope(input_value integer) RETURNS TABLE(value text) LANGUAGE plpgsql AS $trap$
BEGIN
 CREATE TEMP TABLE scratch(n integer); INSERT INTO scratch VALUES(input_value); RETURN QUERY SELECT count(*)::text FROM scratch; DROP TABLE scratch;
END;
$trap$;
