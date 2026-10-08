-- Authored public M0 trap; NOT natively qualified.
CREATE OR REPLACE PROCEDURE dbo.trap_ci_unique(input_value text,OUT value text, OUT tsql_return_code integer) LANGUAGE plpgsql AS $trap$
DECLARE mapped_status integer:=0;
BEGIN
 INSERT INTO dbo.names(v) VALUES (input_value); COMMIT; BEGIN INSERT INTO dbo.names(v) VALUES ('a'); EXCEPTION WHEN unique_violation THEN mapped_status:=-4; NULL; END; SELECT count(*)::text, mapped_status INTO value, tsql_return_code FROM dbo.names;
END;
$trap$;
