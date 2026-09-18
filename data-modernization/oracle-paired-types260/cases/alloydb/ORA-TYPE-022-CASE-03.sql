-- Synthetic catalog case ORA-TYPE-022-CASE-03; target AlloyDB PostgreSQL.
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
 SELECT nullif(''::varchar(3), ''), NULL::varchar(3), length('A '::varchar(3)), CASE WHEN ('A'::varchar(3) COLLATE "C") = 'A '::varchar(3) THEN 1 ELSE 0 END
 INTO v_canonical, v_null_value, v_length, v_comparison;
 CREATE TEMP TABLE LY_ORA_TYPE_022_CASE_03 (v varchar(3)) ON COMMIT DROP;
 INSERT INTO pg_temp.LY_ORA_TYPE_022_CASE_03 VALUES ('ABC');
 SELECT v INTO v_boundary FROM pg_temp.LY_ORA_TYPE_022_CASE_03;
 BEGIN
   INSERT INTO pg_temp.LY_ORA_TYPE_022_CASE_03 VALUES ('ABCD');
 EXCEPTION WHEN OTHERS THEN GET STACKED DIAGNOSTICS v_overflow_code = RETURNED_SQLSTATE;
 END;
 SELECT nullif(''::varchar(3), '') INTO v_recovery;
 RAISE NOTICE 'LY_TYPES_OBSERVATION=%', json_build_object('case_id', 'ORA-TYPE-022-CASE-03', 'observations', json_build_object('canonical', v_canonical, 'comparison', v_comparison, 'null_value', v_null_value));
END $pilot$;
ROLLBACK;
