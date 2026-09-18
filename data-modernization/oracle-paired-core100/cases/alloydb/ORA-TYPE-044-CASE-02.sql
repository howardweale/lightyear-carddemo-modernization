-- Synthetic catalog case ORA-TYPE-044-CASE-02; target AlloyDB PostgreSQL.
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
 v_time_value text;
 v_format_a text;
 v_format_b text;
 v_sink text;
 v_length integer; v_comparison integer; v_overflow_code text := '00000';
BEGIN
 SELECT to_char(TIMESTAMP '2026-09-01 12:00:00.123456', 'YYYY-MM-DD"T"HH24:MI:SS.US'), to_char(NULL::timestamp, 'YYYY-MM-DD"T"HH24:MI:SS.US'),
        to_char(CAST(TIMESTAMP '2026-09-01 12:00:00.123456' AS TIMESTAMP(3)), 'YYYY-MM-DD"T"HH24:MI:SS.MS'), to_char(TIMESTAMP '2026-09-01 23:59:59.999999' + INTERVAL '0.000002 second', 'YYYY-MM-DD"T"HH24:MI:SS.US')
 INTO v_canonical, v_null_value, v_boundary, v_time_value;
 BEGIN
   SELECT to_char('2026x09x01 12:00:00.123456'::timestamp, 'YYYY-MM-DD"T"HH24:MI:SS.US') INTO v_sink;
 EXCEPTION WHEN OTHERS THEN GET STACKED DIAGNOSTICS v_overflow_code = RETURNED_SQLSTATE;
 END;
 SELECT to_char(TIMESTAMP '2026-09-01 12:00:00.123456', 'YYYY-MM-DD"T"HH24:MI:SS.US'), to_char(TIMESTAMP '2026-09-01 12:00:00.123456', 'DD/MM/YYYY HH24:MI:SS.US'), to_char(TIMESTAMP '2026-09-01 12:00:00.123456', 'YYYY-MM-DD"T"HH24:MI:SS.US')
 INTO v_recovery, v_format_a, v_format_b;
 RAISE NOTICE 'LY_TYPES_OBSERVATION=%', json_build_object('case_id', 'ORA-TYPE-044-CASE-02', 'observations', json_build_object('format_a', v_format_a, 'format_b', v_format_b, 'null_value', v_null_value));
END $pilot$;
ROLLBACK;
