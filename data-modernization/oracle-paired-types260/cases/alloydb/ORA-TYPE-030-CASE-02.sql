-- Synthetic bounded catalog case ORA-TYPE-030-CASE-02; AlloyDB PostgreSQL.
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
 SELECT rpad((U&'\03A9'::char(3))::text, 3, ' '), NULL::char(3), length(rpad((U&'\03A9'::char(3))::text, 3, ' ')), CASE WHEN U&'\03A9'::char(3) = U&'\03A9  '::char(3) THEN 1 ELSE 0 END
 INTO v_canonical, v_null_value, v_length, v_comparison;
 CREATE TEMP TABLE LY_ORA_TYPE_030_CASE_02 (v char(3)) ON COMMIT DROP;
 INSERT INTO pg_temp.LY_ORA_TYPE_030_CASE_02 VALUES (U&'\03A9\03A9\03A9');
 SELECT v INTO v_boundary FROM pg_temp.LY_ORA_TYPE_030_CASE_02;
 BEGIN
   INSERT INTO pg_temp.LY_ORA_TYPE_030_CASE_02 VALUES (U&'\03A9\03A9\03A9\03A9');
 EXCEPTION WHEN OTHERS THEN GET STACKED DIAGNOSTICS v_overflow_code = RETURNED_SQLSTATE;
 END;
 SELECT rpad((U&'\03A9'::char(3))::text, 3, ' ') INTO v_recovery;
 v_session_value := v_length::text;
 v_canonical := upper(encode(convert_to(v_canonical, 'UTF8'), 'hex'));
 v_boundary := upper(encode(convert_to(v_boundary, 'UTF8'), 'hex'));
 v_recovery := upper(encode(convert_to(v_recovery, 'UTF8'), 'hex'));
 RAISE NOTICE 'LY_TYPES_OBSERVATION=%', json_build_object('case_id', 'ORA-TYPE-030-CASE-02', 'observations', json_build_object('null_value', v_null_value, 'overflow_code', v_overflow_code, 'recovery', v_recovery));
END $pilot$;
ROLLBACK;
