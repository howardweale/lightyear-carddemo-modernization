-- Authored public M0 trap; NOT natively qualified.
CREATE TABLE dbo.effects(id int NOT NULL PRIMARY KEY, amount int NOT NULL);
GO
CREATE TABLE dbo.names(v varchar(20) COLLATE Latin1_General_100_CI_AS NOT NULL UNIQUE);
GO
