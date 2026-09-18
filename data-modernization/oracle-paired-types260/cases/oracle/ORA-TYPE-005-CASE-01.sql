-- Catalog case ORA-TYPE-005-CASE-01; lane 26ai; failure and diagnostic semantics; canonical
-- Every value below comes from an Oracle expression or SQLCODE.
DECLARE
  v_sum VARCHAR2(32); v_null NUMBER; v_rounded VARCHAR2(32); v_maximum VARCHAR2(32);
  v_overflow NUMBER := 0; v_recovery VARCHAR2(32); v_sink NUMBER;
  v_dot VARCHAR2(32); v_comma VARCHAR2(32); v_json VARCHAR2(4000);
BEGIN
  SELECT TO_CHAR(123.45 + 0.55, 'FM990D00', 'NLS_NUMERIC_CHARACTERS=''.,'''),
         CAST(NULL AS NUMBER) + 1,
         TO_CHAR(CAST(2.345 AS NUMBER(3,2)), 'FM990D00', 'NLS_NUMERIC_CHARACTERS=''.,'''),
         TO_CHAR(CAST(999.99 AS NUMBER(5,2)), 'FM990D00', 'NLS_NUMERIC_CHARACTERS=''.,''')
    INTO v_sum, v_null, v_rounded, v_maximum FROM dual;
  BEGIN
    SELECT CAST(1000 AS NUMBER(3,0)) INTO v_sink FROM dual;
  EXCEPTION WHEN OTHERS THEN v_overflow := SQLCODE;
  END;
  SELECT TO_CHAR(123.45 + 0.55, 'FM990D00', 'NLS_NUMERIC_CHARACTERS=''.,''')
    INTO v_recovery FROM dual;
  EXECUTE IMMEDIATE 'ALTER SESSION SET NLS_NUMERIC_CHARACTERS = ''.,''';
  SELECT TO_CHAR(123.45 + 0.55, 'FM990D00') INTO v_dot FROM dual;
  EXECUTE IMMEDIATE 'ALTER SESSION SET NLS_NUMERIC_CHARACTERS = '',.''';
  SELECT TO_CHAR(123.45 + 0.55, 'FM990D00') INTO v_comma FROM dual;
  EXECUTE IMMEDIATE 'ALTER SESSION SET NLS_NUMERIC_CHARACTERS = ''.,''';
  SELECT JSON_OBJECT('case_id' VALUE 'ORA-TYPE-005-CASE-01', 'observations' VALUE
    JSON_OBJECT('overflow_code' VALUE v_overflow,
      'recovery' VALUE v_recovery NULL ON NULL) RETURNING VARCHAR2(4000)) INTO v_json FROM dual;
  DBMS_OUTPUT.PUT_LINE('LY_NUMBER_OBSERVATION=' || v_json);
END;
/
