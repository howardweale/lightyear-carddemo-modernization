-- Synthetic bounded catalog case ORA-TYPE-057-CASE-01; AlloyDB PostgreSQL.
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
 SELECT TO_CHAR((EXTRACT(YEAR FROM INTERVAL '1 year 2 months') * 12 + EXTRACT(MONTH FROM INTERVAL '1 year 2 months')), 'FM9999999990'), TO_CHAR((EXTRACT(YEAR FROM NULL::interval) * 12 + EXTRACT(MONTH FROM NULL::interval)), 'FM9999999990'), TO_CHAR((EXTRACT(YEAR FROM INTERVAL '100 years 1 month') * 12 + EXTRACT(MONTH FROM INTERVAL '100 years 1 month')), 'FM9999999990'), TO_CHAR((EXTRACT(YEAR FROM (-INTERVAL '1 year 2 months')) * 12 + EXTRACT(MONTH FROM (-INTERVAL '1 year 2 months'))), 'FM9999999990'), CASE WHEN INTERVAL '1 year 2 months' > -INTERVAL '1 year 2 months' THEN 1 ELSE 0 END INTO v_canonical, v_null_value, v_boundary, v_session_value, v_comparison;
 BEGIN
 v_sink := ('invalid'::interval)::text;
 EXCEPTION WHEN OTHERS THEN GET STACKED DIAGNOSTICS v_overflow_code = RETURNED_SQLSTATE;
 END;
 SELECT TO_CHAR((EXTRACT(YEAR FROM INTERVAL '1 year 2 months') * 12 + EXTRACT(MONTH FROM INTERVAL '1 year 2 months')), 'FM9999999990') INTO v_recovery;
 RAISE NOTICE 'LY_TYPES_OBSERVATION=%', json_build_object('case_id', 'ORA-TYPE-057-CASE-01', 'observations', json_build_object('null_value', v_null_value));
END $pilot$;
ROLLBACK;
