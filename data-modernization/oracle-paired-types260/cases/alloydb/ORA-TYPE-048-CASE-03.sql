-- Synthetic bounded catalog case ORA-TYPE-048-CASE-03; AlloyDB PostgreSQL.
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
 v_zoned := TIMESTAMPTZ '2026-09-01 17:30:00.123456 +05:30';
 SELECT to_char(v_zoned AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US'), to_char(NULL::timestamptz, 'YYYY-MM-DD"T"HH24:MI:SS.US'),
 to_char(TIMESTAMPTZ '2026-12-31 23:30:00 -01:00' AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US'),
 CASE WHEN v_zoned = TIMESTAMPTZ '2026-09-01 12:00:00.123456 +00:00' THEN 1 ELSE 0 END
 INTO v_canonical, v_null_value, v_boundary, v_comparison;
 BEGIN
 v_sink := ('2026x09x01 12:00:00 +00:00'::timestamptz)::text;
 EXCEPTION WHEN OTHERS THEN GET STACKED DIAGNOSTICS v_overflow_code = RETURNED_SQLSTATE;
 END;
 v_recovery := to_char(v_zoned AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US');
 SET LOCAL TIME ZONE INTERVAL '+05:30' HOUR TO MINUTE;
 v_session_value := to_char(v_zoned, 'YYYY-MM-DD"T"HH24:MI:SS.US');
 RAISE NOTICE 'LY_TYPES_OBSERVATION=%', json_build_object('case_id', 'ORA-TYPE-048-CASE-03', 'observations', json_build_object('boundary', v_boundary, 'comparison', v_comparison, 'session_value', v_session_value));
END $pilot$;
ROLLBACK;
