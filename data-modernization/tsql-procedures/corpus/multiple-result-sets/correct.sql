-- Authored public M0 trap; NOT natively qualified.
CREATE OR REPLACE PROCEDURE dbo.trap(INOUT first_set refcursor,INOUT second_set refcursor) LANGUAGE plpgsql AS $$ BEGIN OPEN first_set FOR SELECT 'first'::text AS value; OPEN second_set FOR SELECT 'second'::text AS value; END; $$;
