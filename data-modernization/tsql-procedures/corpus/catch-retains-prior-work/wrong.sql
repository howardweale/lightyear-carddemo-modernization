-- Authored public M0 trap; NOT natively qualified.
CREATE OR REPLACE FUNCTION dbo.trap() RETURNS TABLE(value text, tsql_return_code integer) LANGUAGE plpgsql AS $trap$
DECLARE mapped_status integer:=0;
BEGIN
 BEGIN INSERT INTO dbo.effects VALUES(1,10); PERFORM 1/0; EXCEPTION WHEN division_by_zero THEN mapped_status:=-6; INSERT INTO dbo.effects VALUES(2,20); END; RETURN QUERY SELECT count(*)::text, mapped_status FROM dbo.effects;
END;
$trap$;
