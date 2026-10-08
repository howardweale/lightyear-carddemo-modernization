CREATE TABLE dbo.effects(id int NOT NULL PRIMARY KEY, amount int NOT NULL);
GO
CREATE TABLE dbo.names(v varchar(20) COLLATE Latin1_General_100_BIN2 NOT NULL UNIQUE);
GO
ALTER TABLE dbo.names ADD CONSTRAINT names_upper CHECK(v COLLATE Latin1_General_100_BIN2 <> 'a');
GO
