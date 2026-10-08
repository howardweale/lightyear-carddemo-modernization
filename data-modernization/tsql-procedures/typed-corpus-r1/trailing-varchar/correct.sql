-- Authored public M0 trap; NOT natively qualified.
CREATE OR REPLACE FUNCTION dbo.trap_trailing_varchar(input_value text) RETURNS TABLE(value text) LANGUAGE plpgsql AS $trap$
BEGIN
 RETURN QUERY SELECT (CASE WHEN rtrim(input_value)=rtrim('A') THEN 1 ELSE 0 END)::text;
END;
$trap$;
