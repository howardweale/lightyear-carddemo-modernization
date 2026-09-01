-- LIGHTYEAR MS #49 native Oracle fixture harness
-- Source authority: oracle-samples/db-sample-schemas v23.3 at e3325a83e56c516815844025418a96ecaf219751
-- This script emits LY49|<fixture-id>|PASS or raises an application error.
SET SERVEROUTPUT ON
SET DEFINE OFF
WHENEVER SQLERROR EXIT SQL.SQLCODE ROLLBACK

DECLARE
  v VARCHAR2(1) := '';
BEGIN
  IF v IS NOT NULL OR ' ' IS NULL THEN RAISE_APPLICATION_ERROR(-20001, 'empty-string-null'); END IF;
  DBMS_OUTPUT.PUT_LINE('LY49|oracle-empty-string-null|PASS');
END;
/

BEGIN EXECUTE IMMEDIATE 'DROP TABLE ly49_number_probe PURGE'; EXCEPTION WHEN OTHERS THEN IF SQLCODE != -942 THEN RAISE; END IF; END;
/
CREATE TABLE ly49_number_probe (v NUMBER(3,2));
DECLARE
  a NUMBER(6,1) := 123.89;
  b NUMBER(4,5) := .000127;
  overflow_seen BOOLEAN := FALSE;
BEGIN
  BEGIN INSERT INTO ly49_number_probe VALUES (123.89); EXCEPTION WHEN OTHERS THEN overflow_seen := SQLCODE = -1438; END;
  IF a != 123.9 OR b != .00013 OR NOT overflow_seen THEN RAISE_APPLICATION_ERROR(-20002, 'number'); END IF;
  DBMS_OUTPUT.PUT_LINE('LY49|oracle-number-precision-scale|PASS');
END;
/
DROP TABLE ly49_number_probe PURGE;

DECLARE
  d DATE := TO_DATE('2024-02-29 23:59:59', 'YYYY-MM-DD HH24:MI:SS');
BEGIN
  IF TO_CHAR(d + 1/86400, 'YYYY-MM-DD HH24:MI:SS') != '2024-03-01 00:00:00'
     OR TO_CHAR(TRUNC(d), 'YYYY-MM-DD HH24:MI:SS') != '2024-02-29 00:00:00'
  THEN RAISE_APPLICATION_ERROR(-20003, 'date'); END IF;
  DBMS_OUTPUT.PUT_LINE('LY49|oracle-date-time-arithmetic|PASS');
END;
/

BEGIN
  IF NVL('', 'fallback') != 'fallback' OR DECODE(NULL, NULL, 'match', 'miss') != 'match'
  THEN RAISE_APPLICATION_ERROR(-20004, 'nvl-decode'); END IF;
  DBMS_OUTPUT.PUT_LINE('LY49|oracle-nvl-decode-coercion|PASS');
END;
/

DECLARE
  before_order VARCHAR2(20);
  after_order VARCHAR2(20);
  impossible NUMBER;
BEGIN
  WITH values_in_fetch_order (seq, v) AS (SELECT 1,3 FROM dual UNION ALL SELECT 2,1 FROM dual UNION ALL SELECT 3,2 FROM dual)
  SELECT LISTAGG(v, ',') WITHIN GROUP (ORDER BY v) INTO before_order
    FROM (SELECT v FROM (SELECT v FROM values_in_fetch_order ORDER BY seq) WHERE ROWNUM <= 2);
  WITH values_to_sort (v) AS (SELECT 3 FROM dual UNION ALL SELECT 1 FROM dual UNION ALL SELECT 2 FROM dual)
  SELECT LISTAGG(v, ',') WITHIN GROUP (ORDER BY v) INTO after_order
    FROM (SELECT v FROM (SELECT v FROM values_to_sort ORDER BY v) WHERE ROWNUM <= 2);
  SELECT COUNT(*) INTO impossible FROM dual WHERE ROWNUM > 1;
  IF before_order != '1,3' OR after_order != '1,2' OR impossible != 0
  THEN RAISE_APPLICATION_ERROR(-20005, 'rownum'); END IF;
  DBMS_OUTPUT.PUT_LINE('LY49|oracle-rownum-ordering|PASS');
END;
/

BEGIN EXECUTE IMMEDIATE 'DROP TABLE ly49_sequence PURGE'; EXCEPTION WHEN OTHERS THEN IF SQLCODE != -942 THEN RAISE; END IF; END;
/
CREATE TABLE ly49_sequence (id NUMBER PRIMARY KEY, current_value NUMBER NOT NULL);
INSERT INTO ly49_sequence VALUES (1, 100);
COMMIT;
DECLARE
  v NUMBER;
BEGIN
  SELECT current_value INTO v FROM ly49_sequence WHERE id = 1 FOR UPDATE;
  UPDATE ly49_sequence SET current_value = v + 1 WHERE id = 1;
  SAVEPOINT before_second;
  UPDATE ly49_sequence SET current_value = current_value + 1 WHERE id = 1;
  ROLLBACK TO before_second;
  SELECT current_value INTO v FROM ly49_sequence WHERE id = 1;
  IF v != 101 THEN RAISE_APPLICATION_ERROR(-20006, 'for-update-sequence'); END IF;
  COMMIT;
  DBMS_OUTPUT.PUT_LINE('LY49|oracle-select-for-update-sequence|PASS');
END;
/
DROP TABLE ly49_sequence PURGE;

DECLARE
  v NUMBER;
  no_data_seen BOOLEAN := FALSE;
  too_many_seen BOOLEAN := FALSE;
BEGIN
  BEGIN SELECT 1 INTO v FROM dual WHERE 1 = 0; EXCEPTION WHEN NO_DATA_FOUND THEN no_data_seen := TRUE; END;
  BEGIN SELECT column_value INTO v FROM TABLE(sys.odcinumberlist(1,2)); EXCEPTION WHEN TOO_MANY_ROWS THEN too_many_seen := TRUE; END;
  IF NOT no_data_seen OR NOT too_many_seen THEN RAISE_APPLICATION_ERROR(-20007, 'select-into'); END IF;
  DBMS_OUTPUT.PUT_LINE('LY49|oracle-select-into-no-data-found|PASS');
END;
/

BEGIN EXECUTE IMMEDIATE 'DROP TABLE ly49_lobs PURGE'; EXCEPTION WHEN OTHERS THEN IF SQLCODE != -942 THEN RAISE; END IF; END;
/
CREATE TABLE ly49_lobs (id NUMBER PRIMARY KEY, binary_value BLOB, character_value CLOB);
INSERT INTO ly49_lobs VALUES (1, HEXTORAW('0001FF'), TO_CLOB('Lightyear Oracle dialect'));
DECLARE
  blob_length NUMBER;
  clob_length NUMBER;
BEGIN
  SELECT DBMS_LOB.GETLENGTH(binary_value), DBMS_LOB.GETLENGTH(character_value)
    INTO blob_length, clob_length FROM ly49_lobs WHERE id = 1;
  IF blob_length != 3 OR clob_length != 24 THEN RAISE_APPLICATION_ERROR(-20008, 'lob'); END IF;
  ROLLBACK;
  DBMS_OUTPUT.PUT_LINE('LY49|oracle-lob-boundaries|PASS');
END;
/
DROP TABLE ly49_lobs PURGE;
EXIT SUCCESS
