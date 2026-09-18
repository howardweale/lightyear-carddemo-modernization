-- Synthetic catalog case ORA-TYPE-036-CASE-04; source Oracle 26ai.
DECLARE
  v_canonical VARCHAR2(128);
  v_null_value VARCHAR2(128);
  v_boundary VARCHAR2(128);
  v_recovery VARCHAR2(128);
  v_time_value VARCHAR2(128);
  v_format_a VARCHAR2(128);
  v_format_b VARCHAR2(128);
  v_sink VARCHAR2(128);
  v_length NUMBER; v_comparison NUMBER; v_overflow_code NUMBER := 0; v_json VARCHAR2(4000);
BEGIN
  SELECT TO_CHAR(DATE '2024-02-29' + 1, 'YYYY-MM-DD"T"HH24:MI:SS'), TO_CHAR(CAST(NULL AS DATE), 'YYYY-MM-DD"T"HH24:MI:SS'),
         TO_CHAR(DATE '2024-02-29' + 1, 'YYYY-MM-DD"T"HH24:MI:SS'), TO_CHAR(TO_DATE('2024-02-29 23:59:59','YYYY-MM-DD HH24:MI:SS'), 'YYYY-MM-DD"T"HH24:MI:SS')
    INTO v_canonical, v_null_value, v_boundary, v_time_value FROM dual;
  BEGIN
    SELECT TO_CHAR(TO_DATE('2024x03x01','FXYYYY-MM-DD'), 'YYYY-MM-DD"T"HH24:MI:SS') INTO v_sink FROM dual;
  EXCEPTION WHEN OTHERS THEN v_overflow_code := SQLCODE;
  END;
  SELECT TO_CHAR(DATE '2024-02-29' + 1, 'YYYY-MM-DD"T"HH24:MI:SS') INTO v_recovery FROM dual;
  EXECUTE IMMEDIATE 'ALTER SESSION SET NLS_DATE_FORMAT = ''DD/MM/YYYY''';
  SELECT TO_CHAR(DATE '2024-02-29' + 1) INTO v_format_a FROM dual;
  EXECUTE IMMEDIATE 'ALTER SESSION SET NLS_DATE_FORMAT = ''YYYY-MM-DD''';
  SELECT TO_CHAR(DATE '2024-02-29' + 1) INTO v_format_b FROM dual;
  SELECT JSON_OBJECT('case_id' VALUE 'ORA-TYPE-036-CASE-04', 'observations' VALUE
    JSON_OBJECT('canonical' VALUE v_canonical, 'overflow_code' VALUE v_overflow_code, 'recovery' VALUE v_recovery NULL ON NULL) RETURNING VARCHAR2(4000)) INTO v_json FROM dual;
  DBMS_OUTPUT.PUT_LINE('LY_TYPES_OBSERVATION=' || v_json);
END;
/
