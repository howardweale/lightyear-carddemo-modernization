-- Authored public M0 trap; NOT natively qualified.
CREATE OR ALTER PROCEDURE dbo.trap
AS
BEGIN
 SET NOCOUNT ON;
 MERGE dbo.effects AS t USING (VALUES(1,20),(2,30)) AS s(id,amount) ON t.id=s.id WHEN MATCHED THEN UPDATE SET amount=s.amount WHEN NOT MATCHED THEN INSERT(id,amount) VALUES(s.id,s.amount); SELECT CONVERT(varchar(20),SUM(amount)) AS value FROM dbo.effects;
END;
GO
