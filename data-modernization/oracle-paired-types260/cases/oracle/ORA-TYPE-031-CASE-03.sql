-- Synthetic bounded catalog case ORA-TYPE-031-CASE-03; Oracle 26ai.
DECLARE
 v_canonical VARCHAR2(128);
 v_null_value VARCHAR2(128);
 v_boundary VARCHAR2(128);
 v_recovery VARCHAR2(128);
 v_session_value VARCHAR2(128);
 v_sink VARCHAR2(128);
 v_zoned TIMESTAMP WITH TIME ZONE;
 v_length NUMBER; v_comparison NUMBER; v_overflow_code NUMBER := 0; v_json VARCHAR2(4000);
BEGIN
 SELECT RAWTOHEX(HEXTORAW('00017FFF')), RAWTOHEX(NULL), RAWTOHEX(HEXTORAW('FFFF')), TO_CHAR(UTL_RAW.LENGTH(HEXTORAW('00017FFF')), 'FM9990'), CASE WHEN HEXTORAW('00ff') = HEXTORAW('00FF') THEN 1 ELSE 0 END INTO v_canonical, v_null_value, v_boundary, v_session_value, v_comparison FROM dual;
 BEGIN
 SELECT RAWTOHEX(HEXTORAW('GG')) INTO v_sink FROM dual;
 EXCEPTION WHEN OTHERS THEN v_overflow_code := SQLCODE;
 END;
 SELECT RAWTOHEX(HEXTORAW('00017FFF')) INTO v_recovery FROM dual;
 SELECT JSON_OBJECT('case_id' VALUE 'ORA-TYPE-031-CASE-03', 'observations' VALUE
 JSON_OBJECT('canonical' VALUE v_canonical, 'comparison' VALUE v_comparison, 'session_value' VALUE v_session_value NULL ON NULL) RETURNING VARCHAR2(4000)) INTO v_json FROM dual;
 DBMS_OUTPUT.PUT_LINE('LY_TYPES_OBSERVATION=' || v_json);
END;
/
