CREATE SCHEMA IF NOT EXISTS carddemo;

DROP TABLE IF EXISTS carddemo.authfrds;

CREATE TABLE carddemo.authfrds (
  "card_num" CHAR(16) NOT NULL,
  "auth_ts" TIMESTAMP(6) NOT NULL,
  "auth_type" CHAR(4),
  "card_expiry_date" CHAR(4),
  "message_type" CHAR(6),
  "message_source" CHAR(6),
  "auth_id_code" CHAR(6),
  "auth_resp_code" CHAR(2),
  "auth_resp_reason" CHAR(4),
  "processing_code" CHAR(6),
  "transaction_amt" NUMERIC(12,2),
  "approved_amt" NUMERIC(12,2),
  "merchant_catagory_code" CHAR(4),
  "acqr_country_code" CHAR(3),
  "pos_entry_mode" SMALLINT,
  "merchant_id" CHAR(15),
  "merchant_name" VARCHAR(22),
  "merchant_city" CHAR(13),
  "merchant_state" CHAR(2),
  "merchant_zip" CHAR(9),
  "transaction_id" CHAR(15),
  "match_status" CHAR(1),
  "auth_fraud" CHAR(1),
  "fraud_rpt_date" DATE,
  "acct_id" NUMERIC(11,0),
  "cust_id" NUMERIC(9,0),
  CONSTRAINT "pk_authfrds" PRIMARY KEY ("card_num", "auth_ts")
);

CREATE UNIQUE INDEX "xauthfrd" ON carddemo.authfrds ("card_num" ASC, "auth_ts" DESC);
