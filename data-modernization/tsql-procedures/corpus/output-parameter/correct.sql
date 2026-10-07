-- Authored public M0 trap; NOT natively qualified.
CREATE OR REPLACE PROCEDURE dbo.trap(INOUT answer integer) LANGUAGE plpgsql AS $$ BEGIN answer:=7; END; $$;
