-- Authored public M0 trap; NOT natively qualified.
CREATE OR REPLACE FUNCTION dbo.trap() RETURNS TABLE(value text, tsql_return_code integer) LANGUAGE plpgsql AS $trap$
DECLARE mapped_status integer:=0;
BEGIN
 INSERT INTO dbo.names(v) VALUES ('A'); BEGIN INSERT INTO dbo.names(v) VALUES ('a'); EXCEPTION WHEN unique_violation THEN mapped_status:=-4; NULL; END; RETURN QUERY SELECT count(*)::text, mapped_status FROM dbo.names;
END;
$trap$;
