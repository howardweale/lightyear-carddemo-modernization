-- Authored public M0 trap; NOT natively qualified.
CREATE OR REPLACE FUNCTION dbo.trap_datetime_002(milliseconds integer) RETURNS TABLE(value text) LANGUAGE plpgsql AS $trap$
BEGIN
 RETURN QUERY SELECT (to_char(timestamp '2026-10-01'+(round(milliseconds::numeric*0.3)/0.3)*interval '1 millisecond','YYYY-MM-DD HH24:MI:SS.MS'))::text;
END;
$trap$;
