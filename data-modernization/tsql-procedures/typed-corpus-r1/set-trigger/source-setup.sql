-- Authored public M0 trap; NOT natively qualified.
CREATE TABLE dbo.effects(id int NOT NULL PRIMARY KEY, amount int NOT NULL);
GO
CREATE TABLE dbo.audit(total int);
GO
CREATE TRIGGER dbo.effects_audit ON dbo.effects AFTER INSERT AS BEGIN SET NOCOUNT ON; INSERT dbo.audit(total) SELECT SUM(amount) FROM inserted; END;
GO
