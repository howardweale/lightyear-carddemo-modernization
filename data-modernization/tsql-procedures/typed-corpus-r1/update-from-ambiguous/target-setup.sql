-- Authored public M0 trap; NOT natively qualified.
CREATE SCHEMA IF NOT EXISTS dbo;
CREATE TABLE dbo.effects(id integer PRIMARY KEY, amount integer NOT NULL);
CREATE TABLE dbo.matches(k integer,v integer); INSERT INTO dbo.matches VALUES(1,10),(1,20); INSERT INTO dbo.effects VALUES(1,0);
