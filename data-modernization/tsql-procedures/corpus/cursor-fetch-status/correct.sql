-- Authored public M0 trap; NOT natively qualified.
CREATE OR REPLACE FUNCTION dbo.trap() RETURNS TABLE(value text) LANGUAGE plpgsql AS $trap$
DECLARE n integer; total integer:=0;
BEGIN
 FOR n IN SELECT v FROM (VALUES(1),(2),(3)) x(v) ORDER BY v LOOP total:=total+n; END LOOP; RETURN QUERY SELECT total::text;
END;
$trap$;
