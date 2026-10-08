-- Authored public M0 trap; NOT natively qualified.
CREATE OR REPLACE PROCEDURE dbo.trap_default_return_code(input_value integer,INOUT return_code integer) LANGUAGE plpgsql AS $$ BEGIN PERFORM input_value; return_code:=1; END; $$;
