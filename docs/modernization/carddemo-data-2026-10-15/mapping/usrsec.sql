CREATE TABLE "usrsec" (
  source_ordinal bigint NOT NULL UNIQUE,
  encoding_meta jsonb NOT NULL,
  source_sha256 char(64) NOT NULL,
  "ebcdic_key" bytea NOT NULL PRIMARY KEY,
  "sec_user_data_sec_usr_id" char(8) NOT NULL,
  "sec_user_data_sec_usr_fname" char(20) NOT NULL,
  "sec_user_data_sec_usr_lname" char(20) NOT NULL,
  "sec_user_data_sec_usr_pwd" char(8) NOT NULL,
  "sec_user_data_sec_usr_type" char(1) NOT NULL,
  "sec_user_data_sec_usr_filler" char(23) NOT NULL
);
CREATE UNIQUE INDEX ON "usrsec" ("ebcdic_key");
CREATE TABLE "quarantine_usrsec" (source_ordinal bigint PRIMARY KEY, raw_record bytea NOT NULL, reason text NOT NULL, source_sha256 char(64) NOT NULL);
