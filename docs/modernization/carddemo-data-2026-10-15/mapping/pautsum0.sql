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
  "pautsum0_pa_auth_status" char(1) NOT NULL,
  "pautsum0_pa_credit_limit" numeric(11,2) NOT NULL,
  "pautsum0_pa_cash_limit" numeric(11,2) NOT NULL,
  "pautsum0_pa_credit_balance" numeric(11,2) NOT NULL,
  "pautsum0_pa_cash_balance" numeric(11,2) NOT NULL,
  "pautsum0_pa_approved_auth_cnt" numeric(4,0) NOT NULL,
  "pautsum0_pa_declined_auth_cnt" numeric(4,0) NOT NULL,
  "pautsum0_pa_approved_auth_amt" numeric(11,2) NOT NULL,
  "pautsum0_pa_declined_auth_amt" numeric(11,2) NOT NULL
);
CREATE TABLE "pautsum0_pautsum0_pa_account_status" (source_ordinal bigint NOT NULL REFERENCES "pautsum0"(source_ordinal) ON DELETE CASCADE, ordinal integer NOT NULL CHECK (ordinal > 0), "pautsum0_pa_account_status" char(2) NOT NULL, PRIMARY KEY (source_ordinal, ordinal));
CREATE UNIQUE INDEX ON "pautsum0" ("ebcdic_key");
CREATE INDEX ON "pautsum0" (parent_path_key, twin_seq);
CREATE TABLE "quarantine_pautsum0" (source_ordinal bigint PRIMARY KEY, raw_record bytea NOT NULL, reason text NOT NULL, source_sha256 char(64) NOT NULL);
