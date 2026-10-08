-- Authored public M0 trap; NOT natively qualified.
CREATE OR REPLACE FUNCTION dbo.trap_update_from_ambiguous(match_id integer) RETURNS TABLE(value text) LANGUAGE plpgsql AS $trap$
BEGIN
 UPDATE dbo.effects e SET amount=m.v FROM dbo.matches m WHERE e.id=m.k AND e.id=match_id; RETURN QUERY SELECT amount::text FROM dbo.effects;
END;
$trap$;
