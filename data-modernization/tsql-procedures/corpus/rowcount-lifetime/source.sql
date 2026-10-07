-- Authored public M0 trap; NOT natively qualified.
CREATE OR ALTER PROCEDURE dbo.trap
AS
BEGIN
 SET NOCOUNT ON;
 DECLARE @n int; INSERT dbo.effects VALUES(1,10),(2,20); SET @n=@@ROWCOUNT; SELECT CONVERT(varchar(20),@n) AS value;
END;
GO
