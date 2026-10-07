-- Authored public M0 trap; NOT natively qualified.
CREATE OR REPLACE FUNCTION dbo.trap() RETURNS TABLE(value text) LANGUAGE plpgsql AS $trap$
BEGIN
 INSERT INTO dbo.items(v) VALUES(7); RETURN QUERY SELECT lastval()::text;
END;
$trap$;
