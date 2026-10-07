-- Authored public M0 trap; NOT natively qualified.
CREATE OR REPLACE FUNCTION dbo.trap() RETURNS TABLE(value text) LANGUAGE plpgsql AS $trap$
BEGIN
 RETURN QUERY SELECT (CASE WHEN lower('Alpha')=lower('alpha') THEN 1 ELSE 0 END)::text;
END;
$trap$;
