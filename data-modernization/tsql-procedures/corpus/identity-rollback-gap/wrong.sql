-- Authored public M0 trap; NOT natively qualified.
CREATE OR REPLACE FUNCTION dbo.trap() RETURNS TABLE(value text) LANGUAGE plpgsql AS $trap$
DECLARE saved integer;
BEGIN
 BEGIN INSERT INTO dbo.items(v) VALUES(1); RAISE EXCEPTION 'rollback'; EXCEPTION WHEN SQLSTATE 'P0001' THEN NULL; END; ALTER SEQUENCE dbo.items_id_seq RESTART WITH 1; INSERT INTO dbo.items(v) VALUES(2) RETURNING id INTO saved; RETURN QUERY SELECT saved::text;
END;
$trap$;
