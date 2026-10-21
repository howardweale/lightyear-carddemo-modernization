CREATE TABLE "acctdata" (
  source_ordinal bigint NOT NULL UNIQUE,
  encoding_meta jsonb NOT NULL,
  source_sha256 char(64) NOT NULL,
  "ebcdic_key" bytea NOT NULL PRIMARY KEY,
  "account_record_acct_id" numeric(11,0) NOT NULL,
  "account_record_acct_active_status" bytea NOT NULL,
  "account_record_acct_curr_bal" numeric(12,2) NOT NULL,
  "account_record_acct_credit_limit" numeric(12,2) NOT NULL,
  "account_record_acct_cash_credit_limit" numeric(12,2) NOT NULL,
  "account_record_acct_open_date" date NOT NULL,
  "account_record_acct_open_date_raw" char(10) NOT NULL,
  "account_record_acct_expiraion_date" date NOT NULL,
  "account_record_acct_expiraion_date_raw" char(10) NOT NULL,
  "account_record_acct_reissue_date" date NOT NULL,
  "account_record_acct_reissue_date_raw" char(10) NOT NULL,
  "account_record_acct_curr_cyc_credit" numeric(12,2) NOT NULL,
  "account_record_acct_curr_cyc_debit" numeric(12,2) NOT NULL,
  "account_record_acct_addr_zip" bytea NOT NULL,
  "account_record_acct_group_id" bytea NOT NULL
);
CREATE UNIQUE INDEX ON "acctdata" ("ebcdic_key");
CREATE TABLE "quarantine_acctdata" (source_ordinal bigint PRIMARY KEY, raw_record bytea NOT NULL, reason text NOT NULL, source_sha256 char(64) NOT NULL);

CREATE TABLE "custdata" (
  source_ordinal bigint NOT NULL UNIQUE,
  encoding_meta jsonb NOT NULL,
  source_sha256 char(64) NOT NULL,
  "ebcdic_key" bytea NOT NULL PRIMARY KEY,
  "customer_record_cust_id" numeric(9,0) NOT NULL,
  "customer_record_cust_first_name" bytea NOT NULL,
  "customer_record_cust_middle_name" bytea NOT NULL,
  "customer_record_cust_last_name" bytea NOT NULL,
  "customer_record_cust_addr_line_1" bytea NOT NULL,
  "customer_record_cust_addr_line_2" bytea NOT NULL,
  "customer_record_cust_addr_line_3" bytea NOT NULL,
  "customer_record_cust_addr_state_cd" bytea NOT NULL,
  "customer_record_cust_addr_country_cd" bytea NOT NULL,
  "customer_record_cust_addr_zip" bytea NOT NULL,
  "customer_record_cust_phone_num_1" bytea NOT NULL,
  "customer_record_cust_phone_num_2" bytea NOT NULL,
  "customer_record_cust_ssn" numeric(9,0) NOT NULL,
  "customer_record_cust_govt_issued_id" bytea NOT NULL,
  "customer_record_cust_dob_yyyy_mm_dd" date NOT NULL,
  "customer_record_cust_dob_yyyy_mm_dd_raw" char(10) NOT NULL,
  "customer_record_cust_eft_account_id" bytea NOT NULL,
  "customer_record_cust_pri_card_holder_ind" bytea NOT NULL,
  "customer_record_cust_fico_credit_score" numeric(3,0) NOT NULL
);
CREATE UNIQUE INDEX ON "custdata" ("ebcdic_key");
CREATE TABLE "quarantine_custdata" (source_ordinal bigint PRIMARY KEY, raw_record bytea NOT NULL, reason text NOT NULL, source_sha256 char(64) NOT NULL);

CREATE TABLE "carddata" (
  source_ordinal bigint NOT NULL UNIQUE,
  encoding_meta jsonb NOT NULL,
  source_sha256 char(64) NOT NULL,
  "ebcdic_key" bytea NOT NULL PRIMARY KEY,
  "ebcdic_key_aix_1" bytea NOT NULL,
  "card_record_card_num" bytea NOT NULL,
  "card_record_card_acct_id" numeric(11,0) NOT NULL,
  "card_record_card_cvv_cd" numeric(3,0) NOT NULL,
  "card_record_card_embossed_name" bytea NOT NULL,
  "card_record_card_expiraion_date" date NOT NULL,
  "card_record_card_expiraion_date_raw" char(10) NOT NULL,
  "card_record_card_active_status" bytea NOT NULL
);
CREATE UNIQUE INDEX ON "carddata" ("ebcdic_key");
CREATE INDEX ON "carddata" ("ebcdic_key_aix_1");
CREATE TABLE "quarantine_carddata" (source_ordinal bigint PRIMARY KEY, raw_record bytea NOT NULL, reason text NOT NULL, source_sha256 char(64) NOT NULL);

CREATE TABLE "cardxref" (
  source_ordinal bigint NOT NULL UNIQUE,
  encoding_meta jsonb NOT NULL,
  source_sha256 char(64) NOT NULL,
  "ebcdic_key" bytea NOT NULL PRIMARY KEY,
  "ebcdic_key_aix_1" bytea NOT NULL,
  "card_xref_record_xref_card_num" bytea NOT NULL,
  "card_xref_record_xref_cust_id" numeric(9,0) NOT NULL,
  "card_xref_record_xref_acct_id" numeric(11,0) NOT NULL
);
CREATE UNIQUE INDEX ON "cardxref" ("ebcdic_key");
CREATE INDEX ON "cardxref" ("ebcdic_key_aix_1");
CREATE TABLE "quarantine_cardxref" (source_ordinal bigint PRIMARY KEY, raw_record bytea NOT NULL, reason text NOT NULL, source_sha256 char(64) NOT NULL);

CREATE TABLE "usrsec" (
  source_ordinal bigint NOT NULL UNIQUE,
  encoding_meta jsonb NOT NULL,
  source_sha256 char(64) NOT NULL,
  "ebcdic_key" bytea NOT NULL PRIMARY KEY,
  "sec_user_data_sec_usr_id" bytea NOT NULL,
  "sec_user_data_sec_usr_fname" bytea NOT NULL,
  "sec_user_data_sec_usr_lname" bytea NOT NULL,
  "sec_user_data_sec_usr_pwd" bytea NOT NULL,
  "sec_user_data_sec_usr_type" bytea NOT NULL,
  "sec_user_data_sec_usr_filler" bytea NOT NULL
);
CREATE UNIQUE INDEX ON "usrsec" ("ebcdic_key");
CREATE TABLE "quarantine_usrsec" (source_ordinal bigint PRIMARY KEY, raw_record bytea NOT NULL, reason text NOT NULL, source_sha256 char(64) NOT NULL);

CREATE TABLE "pautsum0" (
  source_ordinal bigint NOT NULL UNIQUE,
  encoding_meta jsonb NOT NULL,
  source_sha256 char(64) NOT NULL,
  "ebcdic_key" bytea NOT NULL PRIMARY KEY,
  path_key bytea NOT NULL UNIQUE,
  parent_path_key bytea,
  twin_seq bigint NOT NULL CHECK (twin_seq >= 0),
  "pautsum0_pa_acct_id" numeric(11,0) NOT NULL,
  "pautsum0_pa_cust_id" numeric(9,0) NOT NULL,
  "pautsum0_pa_auth_status" bytea NOT NULL,
  "pautsum0_pa_credit_limit" numeric(11,2) NOT NULL,
  "pautsum0_pa_cash_limit" numeric(11,2) NOT NULL,
  "pautsum0_pa_credit_balance" numeric(11,2) NOT NULL,
  "pautsum0_pa_cash_balance" numeric(11,2) NOT NULL,
  "pautsum0_pa_approved_auth_cnt" numeric(4,0) NOT NULL,
  "pautsum0_pa_declined_auth_cnt" numeric(4,0) NOT NULL,
  "pautsum0_pa_approved_auth_amt" numeric(11,2) NOT NULL,
  "pautsum0_pa_declined_auth_amt" numeric(11,2) NOT NULL
);
CREATE TABLE "pautsum0_pautsum0_pa_account_status" (source_ordinal bigint NOT NULL REFERENCES "pautsum0"(source_ordinal) ON DELETE CASCADE, ordinal integer NOT NULL CHECK (ordinal > 0), "pautsum0_pa_account_status" bytea NOT NULL, PRIMARY KEY (source_ordinal, ordinal));
CREATE UNIQUE INDEX ON "pautsum0" ("ebcdic_key");
CREATE INDEX ON "pautsum0" (parent_path_key, twin_seq);
CREATE TABLE "quarantine_pautsum0" (source_ordinal bigint PRIMARY KEY, raw_record bytea NOT NULL, reason text NOT NULL, source_sha256 char(64) NOT NULL);

CREATE TABLE "pautdtl1" (
  source_ordinal bigint NOT NULL UNIQUE,
  encoding_meta jsonb NOT NULL,
  source_sha256 char(64) NOT NULL,
  "ebcdic_key" bytea NOT NULL PRIMARY KEY,
  path_key bytea NOT NULL UNIQUE,
  parent_path_key bytea,
  twin_seq bigint NOT NULL CHECK (twin_seq >= 0),
  FOREIGN KEY (parent_path_key) REFERENCES "pautsum0"(path_key),
  CHECK (parent_path_key IS NOT NULL),
  "pautdtl1_pa_authorization_key_pa_auth_date_9c" numeric(5,0) NOT NULL,
  "pautdtl1_pa_authorization_key_pa_auth_time_9c" numeric(9,0) NOT NULL,
  "pautdtl1_pa_auth_orig_date" bytea NOT NULL,
  "pautdtl1_pa_auth_orig_time" bytea NOT NULL,
  "pautdtl1_pa_card_num" bytea NOT NULL,
  "pautdtl1_pa_auth_type" bytea NOT NULL,
  "pautdtl1_pa_card_expiry_date" bytea NOT NULL,
  "pautdtl1_pa_message_type" bytea NOT NULL,
  "pautdtl1_pa_message_source" bytea NOT NULL,
  "pautdtl1_pa_auth_id_code" bytea NOT NULL,
  "pautdtl1_pa_auth_resp_code" bytea NOT NULL,
  "pautdtl1_pa_auth_resp_reason" bytea NOT NULL,
  "pautdtl1_pa_processing_code" numeric(6,0) NOT NULL,
  "pautdtl1_pa_transaction_amt" numeric(12,2) NOT NULL,
  "pautdtl1_pa_approved_amt" numeric(12,2) NOT NULL,
  "pautdtl1_pa_merchant_catagory_code" bytea NOT NULL,
  "pautdtl1_pa_acqr_country_code" bytea NOT NULL,
  "pautdtl1_pa_pos_entry_mode" numeric(2,0) NOT NULL,
  "pautdtl1_pa_merchant_id" bytea NOT NULL,
  "pautdtl1_pa_merchant_name" bytea NOT NULL,
  "pautdtl1_pa_merchant_city" bytea NOT NULL,
  "pautdtl1_pa_merchant_state" bytea NOT NULL,
  "pautdtl1_pa_merchant_zip" bytea NOT NULL,
  "pautdtl1_pa_transaction_id" bytea NOT NULL,
  "pautdtl1_pa_match_status" bytea NOT NULL,
  "pautdtl1_pa_auth_fraud" bytea NOT NULL,
  "pautdtl1_pa_fraud_rpt_date" bytea NOT NULL
);
CREATE UNIQUE INDEX ON "pautdtl1" ("ebcdic_key");
CREATE INDEX ON "pautdtl1" (parent_path_key, twin_seq);
CREATE TABLE "quarantine_pautdtl1" (source_ordinal bigint PRIMARY KEY, raw_record bytea NOT NULL, reason text NOT NULL, source_sha256 char(64) NOT NULL);
