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
