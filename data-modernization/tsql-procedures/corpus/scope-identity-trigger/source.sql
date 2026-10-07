-- Authored public M0 trap; NOT natively qualified.
CREATE OR ALTER PROCEDURE dbo.trap
AS
BEGIN
 SET NOCOUNT ON;
 INSERT dbo.items(v) VALUES(7); SELECT CONVERT(varchar(20),CONVERT(int,SCOPE_IDENTITY())) AS value;
END;
GO
