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
