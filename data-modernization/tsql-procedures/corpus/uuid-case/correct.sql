-- Authored public M0 trap; NOT natively qualified.
CREATE OR REPLACE FUNCTION dbo.trap() RETURNS TABLE(value text) LANGUAGE plpgsql AS $trap$
BEGIN
 RETURN QUERY SELECT (lower('A0B1C2D3-E4F5-4678-9012-123456789ABC'::uuid::text))::text;
END;
$trap$;
