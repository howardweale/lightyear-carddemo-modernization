-- Authored public M0 trap; NOT natively qualified.
CREATE OR ALTER PROCEDURE dbo.trap
AS
BEGIN
 SET NOCOUNT ON;
 BEGIN TRAN; INSERT dbo.effects VALUES(1,10); BEGIN TRAN; INSERT dbo.effects VALUES(2,20); COMMIT; ROLLBACK; SELECT CONVERT(varchar(20),COUNT(*)) AS value FROM dbo.effects;
END;
GO
