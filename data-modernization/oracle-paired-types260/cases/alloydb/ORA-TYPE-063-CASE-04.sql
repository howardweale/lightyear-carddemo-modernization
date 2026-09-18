-- Synthetic bounded catalog case ORA-TYPE-063-CASE-04; AlloyDB PostgreSQL.
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
 SELECT TO_CHAR((EXTRACT(DAY FROM INTERVAL '1 day 2 hours 3 minutes 4 seconds') * 86400 + EXTRACT(HOUR FROM INTERVAL '1 day 2 hours 3 minutes 4 seconds') * 3600 + EXTRACT(MINUTE FROM INTERVAL '1 day 2 hours 3 minutes 4 seconds') * 60 + EXTRACT(SECOND FROM INTERVAL '1 day 2 hours 3 minutes 4 seconds')), 'FM9999999990'), TO_CHAR((EXTRACT(DAY FROM NULL::interval) * 86400 + EXTRACT(HOUR FROM NULL::interval) * 3600 + EXTRACT(MINUTE FROM NULL::interval) * 60 + EXTRACT(SECOND FROM NULL::interval)), 'FM9999999990'), TO_CHAR(EXTRACT(SECOND FROM INTERVAL '0.000001 second') * 1000000, 'FM9999999990'), TO_CHAR((EXTRACT(DAY FROM (-INTERVAL '1 day 2 hours 3 minutes 4 seconds')) * 86400 + EXTRACT(HOUR FROM (-INTERVAL '1 day 2 hours 3 minutes 4 seconds')) * 3600 + EXTRACT(MINUTE FROM (-INTERVAL '1 day 2 hours 3 minutes 4 seconds')) * 60 + EXTRACT(SECOND FROM (-INTERVAL '1 day 2 hours 3 minutes 4 seconds'))), 'FM9999999990'), CASE WHEN INTERVAL '1 day 2 hours 3 minutes 4 seconds' > -INTERVAL '1 day 2 hours 3 minutes 4 seconds' THEN 1 ELSE 0 END INTO v_canonical, v_null_value, v_boundary, v_session_value, v_comparison;
 BEGIN
 v_sink := ('invalid'::interval)::text;
 EXCEPTION WHEN OTHERS THEN GET STACKED DIAGNOSTICS v_overflow_code = RETURNED_SQLSTATE;
 END;
 SELECT TO_CHAR((EXTRACT(DAY FROM INTERVAL '1 day 2 hours 3 minutes 4 seconds') * 86400 + EXTRACT(HOUR FROM INTERVAL '1 day 2 hours 3 minutes 4 seconds') * 3600 + EXTRACT(MINUTE FROM INTERVAL '1 day 2 hours 3 minutes 4 seconds') * 60 + EXTRACT(SECOND FROM INTERVAL '1 day 2 hours 3 minutes 4 seconds')), 'FM9999999990') INTO v_recovery;
 RAISE NOTICE 'LY_TYPES_OBSERVATION=%', json_build_object('case_id', 'ORA-TYPE-063-CASE-04', 'observations', json_build_object('boundary', v_boundary, 'overflow_code', v_overflow_code, 'recovery', v_recovery));
END $pilot$;
ROLLBACK;
