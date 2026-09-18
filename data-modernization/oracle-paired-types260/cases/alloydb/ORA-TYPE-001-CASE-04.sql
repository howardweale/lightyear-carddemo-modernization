BEGIN;
SET LOCAL statement_timeout = '10s';
SET LOCAL lc_numeric = 'C';
DO $pilot$
DECLARE
 v_sum text; v_null numeric; v_rounded text; v_maximum text;
 v_overflow text := '00000'; v_recovery text; v_dot text; v_comma text; v_sink numeric;
BEGIN
 SELECT to_char(123.45::numeric + 0.55::numeric, 'FM990D00'), NULL::numeric + 1,
        to_char(2.345::numeric(3,2), 'FM990D00'), to_char(999.99::numeric(5,2), 'FM990D00')
 INTO v_sum, v_null, v_rounded, v_maximum;
 BEGIN
  SELECT 1000::numeric(3,0) INTO v_sink;
 EXCEPTION WHEN OTHERS THEN GET STACKED DIAGNOSTICS v_overflow = RETURNED_SQLSTATE;
 END;
 SELECT to_char(123.45::numeric + 0.55::numeric, 'FM990D00') INTO v_recovery;
 SELECT to_char(123.45::numeric + 0.55::numeric, 'FM990D00') INTO v_dot;
 SELECT replace(to_char(123.45::numeric + 0.55::numeric, 'FM990D00'), '.', ',') INTO v_comma;
 RAISE NOTICE 'LY_PAIRED_OBSERVATION=%', json_build_object('case_id', 'ORA-TYPE-001-CASE-04', 'observations', json_build_object('arithmetic', v_sum, 'overflow_code', v_overflow, 'recovery', v_recovery));
END $pilot$;
ROLLBACK;
