-- Synthetic bounded catalog case ORA-TYPE-015-CASE-02; AlloyDB PostgreSQL.
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
 SELECT upper(encode(float8send(CAST(1.5 AS double precision)), 'hex')), upper(encode(float8send(CAST(NULL AS double precision)), 'hex')), upper(encode(float8send(CAST('2.2250738585072014e-308' AS double precision)), 'hex')), CASE WHEN CAST('-0' AS double precision) = CAST('0' AS double precision) THEN '1' ELSE '0' END, CASE WHEN CAST('NaN' AS double precision) = CAST('NaN' AS double precision) AND CAST('NaN' AS double precision) > CAST('Infinity' AS double precision) THEN 1 ELSE 0 END INTO v_canonical, v_null_value, v_boundary, v_session_value, v_comparison;
 BEGIN
 v_sink := (CAST('not-a-number' AS double precision))::text;
 EXCEPTION WHEN OTHERS THEN GET STACKED DIAGNOSTICS v_overflow_code = RETURNED_SQLSTATE;
 END;
 SELECT upper(encode(float8send(CAST(1.5 AS double precision)), 'hex')) INTO v_recovery;
 RAISE NOTICE 'LY_TYPES_OBSERVATION=%', json_build_object('case_id', 'ORA-TYPE-015-CASE-02', 'observations', json_build_object('null_value', v_null_value, 'overflow_code', v_overflow_code, 'recovery', v_recovery));
END $pilot$;
ROLLBACK;
