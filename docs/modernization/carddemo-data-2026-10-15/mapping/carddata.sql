CREATE TABLE "carddata" (
  source_ordinal bigint NOT NULL UNIQUE,
  encoding_meta jsonb NOT NULL,
  source_sha256 char(64) NOT NULL,
  "ebcdic_key" bytea NOT NULL PRIMARY KEY,
  "ebcdic_key_aix_1" bytea NOT NULL,
  "card_record_card_num" char(16) NOT NULL,
  "card_record_card_acct_id" numeric(11,0) NOT NULL,
  "card_record_card_cvv_cd" numeric(3,0) NOT NULL,
  "card_record_card_embossed_name" char(50) NOT NULL,
  "card_record_card_expiraion_date" date NOT NULL,
  "card_record_card_expiraion_date_raw" char(10) NOT NULL,
  "card_record_card_active_status" char(1) NOT NULL
);
CREATE UNIQUE INDEX ON "carddata" ("ebcdic_key");
CREATE INDEX ON "carddata" ("ebcdic_key_aix_1");
CREATE TABLE "quarantine_carddata" (source_ordinal bigint PRIMARY KEY, raw_record bytea NOT NULL, reason text NOT NULL, source_sha256 char(64) NOT NULL);
