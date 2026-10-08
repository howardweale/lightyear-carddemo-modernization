-- Authored public M0 trap; NOT natively qualified.
CREATE OR ALTER PROCEDURE dbo.trap_identity_rollback_gap @input_value int
AS
BEGIN
 SET NOCOUNT ON;
 BEGIN TRAN; INSERT dbo.items(v) VALUES(1); ROLLBACK; INSERT dbo.items(v) VALUES(@input_value); SELECT CONVERT(varchar(20),CONVERT(int,SCOPE_IDENTITY())) AS value;
END;
GO
