-- Synthetic catalog case ORA-TYPE-038-CASE-02; target AlloyDB PostgreSQL.
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
 SELECT to_char(TIMESTAMP '2024-02-29 00:00:00' + INTERVAL '1 day', 'YYYY-MM-DD"T"HH24:MI:SS'), to_char(NULL::timestamp, 'YYYY-MM-DD"T"HH24:MI:SS'),
        to_char(TIMESTAMP '2024-02-29 00:00:00' + INTERVAL '1 day', 'YYYY-MM-DD"T"HH24:MI:SS'), to_char(TIMESTAMP '2024-02-29 23:59:59', 'YYYY-MM-DD"T"HH24:MI:SS')
 INTO v_canonical, v_null_value, v_boundary, v_time_value;
 BEGIN
   SELECT to_char('2024x03x01'::timestamp, 'YYYY-MM-DD"T"HH24:MI:SS') INTO v_sink;
 EXCEPTION WHEN OTHERS THEN GET STACKED DIAGNOSTICS v_overflow_code = RETURNED_SQLSTATE;
 END;
 SELECT to_char(TIMESTAMP '2024-02-29 00:00:00' + INTERVAL '1 day', 'YYYY-MM-DD"T"HH24:MI:SS'), to_char(TIMESTAMP '2024-02-29 00:00:00' + INTERVAL '1 day', 'DD/MM/YYYY'), to_char(TIMESTAMP '2024-02-29 00:00:00' + INTERVAL '1 day', 'YYYY-MM-DD')
 INTO v_recovery, v_format_a, v_format_b;
 RAISE NOTICE 'LY_TYPES_OBSERVATION=%', json_build_object('case_id', 'ORA-TYPE-038-CASE-02', 'observations', json_build_object('boundary', v_boundary, 'null_value', v_null_value, 'time_value', v_time_value));
END $pilot$;
ROLLBACK;
