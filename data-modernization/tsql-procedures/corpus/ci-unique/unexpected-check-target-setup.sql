CREATE SCHEMA IF NOT EXISTS dbo;
CREATE TABLE dbo.effects(id integer PRIMARY KEY, amount integer NOT NULL);
CREATE TABLE dbo.names(v varchar(20) NOT NULL); CREATE UNIQUE INDEX names_uq ON dbo.names(lower(v));
ALTER TABLE dbo.names ADD CONSTRAINT names_upper CHECK(v <> 'a');
