-- Authored public M0 trap; NOT natively qualified.
CREATE OR REPLACE FUNCTION dbo.trap_cursor_fetch_status(input_value integer) RETURNS TABLE(value text) LANGUAGE plpgsql AS $trap$
DECLARE n integer; total integer:=0;
BEGIN
 FOR n IN SELECT v FROM (VALUES(1),(2),(input_value)) x(v) ORDER BY v LOOP EXIT WHEN n=3; total:=total+n; END LOOP; RETURN QUERY SELECT total::text;
END;
$trap$;
