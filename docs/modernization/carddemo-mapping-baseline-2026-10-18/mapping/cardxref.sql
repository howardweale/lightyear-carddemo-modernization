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
