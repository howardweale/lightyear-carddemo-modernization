-- Authored public M0 trap; NOT natively qualified.
CREATE OR REPLACE FUNCTION dbo.trap() RETURNS TABLE(value text) LANGUAGE plpgsql AS $trap$
DECLARE saved text;
BEGIN
 EXECUTE 'SELECT $1::text' INTO saved USING 'O''Brien'; RETURN QUERY SELECT saved;
END;
$trap$;
