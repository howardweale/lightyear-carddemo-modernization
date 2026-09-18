-- Synthetic bounded catalog case ORA-TYPE-031-CASE-04; AlloyDB PostgreSQL.
BEGIN;
SET LOCAL statement_timeout = '10s';
SET LOCAL TIME ZONE 'UTC';
SET LOCAL DateStyle = 'ISO, YMD';
DO $pilot$
DECLARE
 v_canonical text;
 v_null_value text;
 v_boundary text;
 v_recovery text;
 v_session_value text;
 v_sink text;
 v_zoned timestamptz;
 v_length integer; v_comparison integer; v_overflow_code text := '00000';
BEGIN
 SELECT upper(encode(decode('00017FFF', 'hex'), 'hex')), upper(encode(NULL, 'hex')), upper(encode(decode('FFFF', 'hex'), 'hex')), octet_length(decode('00017FFF', 'hex'))::text, CASE WHEN decode('00ff', 'hex') = decode('00FF', 'hex') THEN 1 ELSE 0 END INTO v_canonical, v_null_value, v_boundary, v_session_value, v_comparison;
 BEGIN
 v_sink := (upper(encode(decode('GG', 'hex'), 'hex')))::text;
 EXCEPTION WHEN OTHERS THEN GET STACKED DIAGNOSTICS v_overflow_code = RETURNED_SQLSTATE;
 END;
 SELECT upper(encode(decode('00017FFF', 'hex'), 'hex')) INTO v_recovery;
 RAISE NOTICE 'LY_TYPES_OBSERVATION=%', json_build_object('case_id', 'ORA-TYPE-031-CASE-04', 'observations', json_build_object('canonical', v_canonical, 'overflow_code', v_overflow_code, 'recovery', v_recovery));
END $pilot$;
ROLLBACK;
