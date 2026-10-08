-- Authored public M0 trap; NOT natively qualified.
CREATE OR REPLACE FUNCTION dbo.trap_xact_abort(arg_amount integer) RETURNS TABLE(value text, tsql_return_code integer) LANGUAGE plpgsql AS $trap$
DECLARE mapped_status integer:=0;
BEGIN
 BEGIN INSERT INTO dbo.effects VALUES(1,arg_amount); mapped_status:=-6; PERFORM 1/0; EXCEPTION WHEN division_by_zero THEN PERFORM 1; END; RETURN QUERY SELECT count(*)::text, mapped_status FROM dbo.effects;
END;
$trap$;
