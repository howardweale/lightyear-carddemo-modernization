-- Authored public M0 trap; NOT natively qualified.
CREATE OR REPLACE PROCEDURE dbo.trap(INOUT return_code integer) LANGUAGE plpgsql AS $$ BEGIN return_code:=1; END; $$;
