-- Authored public M0 trap; NOT natively qualified.
CREATE TABLE dbo.effects(id int NOT NULL PRIMARY KEY, amount int NOT NULL);
GO
CREATE TABLE dbo.items(id int IDENTITY(1,1) PRIMARY KEY,v int);
GO
