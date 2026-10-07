-- Authored public M0 trap; NOT natively qualified.
CREATE TABLE dbo.effects(id int NOT NULL PRIMARY KEY, amount int NOT NULL);
GO
CREATE TABLE dbo.items(id int IDENTITY(1,1) PRIMARY KEY,v int);
CREATE TABLE dbo.audit(id int IDENTITY(100,1) PRIMARY KEY,v int);
GO
CREATE TRIGGER dbo.items_audit ON dbo.items AFTER INSERT AS BEGIN SET NOCOUNT ON; INSERT dbo.audit(v) SELECT v FROM inserted; END;
GO
