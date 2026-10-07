-- Authored public M0 trap; NOT natively qualified.
CREATE OR REPLACE FUNCTION dbo.trap() RETURNS TABLE(value text) LANGUAGE plpgsql AS $trap$
DECLARE n integer;
BEGIN
 INSERT INTO dbo.effects VALUES(1,10),(2,20); PERFORM 1; GET DIAGNOSTICS n=ROW_COUNT; RETURN QUERY SELECT n::text;
END;
$trap$;
