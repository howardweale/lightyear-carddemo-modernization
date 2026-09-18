-- Synthetic bounded catalog case ORA-TYPE-009-CASE-01; AlloyDB PostgreSQL.
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
 SELECT upper(encode(float4send(CAST(1.5 AS real)), 'hex')), upper(encode(float4send(CAST(NULL AS real)), 'hex')), upper(encode(float4send(CAST('1.1754943508222875e-38' AS real)), 'hex')), CASE WHEN CAST('-0' AS real) = CAST('0' AS real) THEN '1' ELSE '0' END, CASE WHEN CAST('NaN' AS real) = CAST('NaN' AS real) AND CAST('NaN' AS real) > CAST('Infinity' AS real) THEN 1 ELSE 0 END INTO v_canonical, v_null_value, v_boundary, v_session_value, v_comparison;
 BEGIN
 v_sink := (CAST('not-a-number' AS real))::text;
 EXCEPTION WHEN OTHERS THEN GET STACKED DIAGNOSTICS v_overflow_code = RETURNED_SQLSTATE;
 END;
 SELECT upper(encode(float4send(CAST(1.5 AS real)), 'hex')) INTO v_recovery;
 RAISE NOTICE 'LY_TYPES_OBSERVATION=%', json_build_object('case_id', 'ORA-TYPE-009-CASE-01', 'observations', json_build_object('comparison', v_comparison, 'session_value', v_session_value));
END $pilot$;
ROLLBACK;
