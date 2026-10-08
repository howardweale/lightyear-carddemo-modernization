CREATE TABLE dbo.effects(id int NOT NULL PRIMARY KEY, amount int NOT NULL);
GO
CREATE TRIGGER dbo.rollback_probe ON dbo.effects AFTER INSERT AS BEGIN SET NOCOUNT ON; ROLLBACK TRANSACTION; DECLARE @zero int=0,@unused int; SET @unused=1/@zero; END;
GO
