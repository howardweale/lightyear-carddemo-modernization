CREATE TABLE "custdata" (
  source_ordinal bigint NOT NULL UNIQUE,
  encoding_meta jsonb NOT NULL,
  source_sha256 char(64) NOT NULL,
  "ebcdic_key" bytea NOT NULL PRIMARY KEY,
  "customer_record_cust_id" numeric(9,0) NOT NULL,
  "customer_record_cust_first_name" char(25) NOT NULL,
  "customer_record_cust_middle_name" char(25) NOT NULL,
  "customer_record_cust_last_name" char(25) NOT NULL,
  "customer_record_cust_addr_line_1" char(50) NOT NULL,
  "customer_record_cust_addr_line_2" char(50) NOT NULL,
  "customer_record_cust_addr_line_3" char(50) NOT NULL,
  "customer_record_cust_addr_state_cd" char(2) NOT NULL,
  "customer_record_cust_addr_country_cd" char(3) NOT NULL,
  "customer_record_cust_addr_zip" char(10) NOT NULL,
  "customer_record_cust_phone_num_1" char(15) NOT NULL,
  "customer_record_cust_phone_num_2" char(15) NOT NULL,
  "customer_record_cust_ssn" numeric(9,0) NOT NULL,
  "customer_record_cust_govt_issued_id" char(20) NOT NULL,
  "customer_record_cust_dob_yyyy_mm_dd" char(10) NOT NULL,
  "customer_record_cust_eft_account_id" char(10) NOT NULL,
  "customer_record_cust_pri_card_holder_ind" char(1) NOT NULL,
  "customer_record_cust_fico_credit_score" numeric(3,0) NOT NULL
);
CREATE UNIQUE INDEX ON "custdata" ("ebcdic_key");
CREATE TABLE "quarantine_custdata" (source_ordinal bigint PRIMARY KEY, raw_record bytea NOT NULL, reason text NOT NULL, source_sha256 char(64) NOT NULL);
