-- Authored public M0 trap; NOT natively qualified.
CREATE TABLE dbo.effects(id int NOT NULL PRIMARY KEY, amount int NOT NULL);
GO
CREATE TABLE dbo.matches(k int,v int); INSERT dbo.matches VALUES(1,10),(1,20); INSERT dbo.effects VALUES(1,0);
GO
