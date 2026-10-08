-- Authored public M0 trap; NOT natively qualified.
CREATE OR REPLACE PROCEDURE dbo.trap_output_parameter(input_value integer,INOUT answer integer) LANGUAGE plpgsql AS $$ BEGIN answer:=input_value; END; $$;
