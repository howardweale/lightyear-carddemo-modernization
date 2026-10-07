-- Authored public M0 trap; NOT natively qualified.
CREATE SCHEMA IF NOT EXISTS dbo;
CREATE TABLE dbo.effects(id integer PRIMARY KEY, amount integer NOT NULL);
INSERT INTO dbo.effects VALUES(1,10);
