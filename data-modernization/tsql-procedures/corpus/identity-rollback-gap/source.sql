-- Authored public M0 trap; NOT natively qualified.
CREATE OR ALTER PROCEDURE dbo.trap
AS
BEGIN
 SET NOCOUNT ON;
 BEGIN TRAN; INSERT dbo.items(v) VALUES(1); ROLLBACK; INSERT dbo.items(v) VALUES(2); SELECT CONVERT(varchar(20),CONVERT(int,SCOPE_IDENTITY())) AS value;
END;
GO
