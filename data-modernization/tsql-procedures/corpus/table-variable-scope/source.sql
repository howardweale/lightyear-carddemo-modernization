-- Authored public M0 trap; NOT natively qualified.
CREATE OR ALTER PROCEDURE dbo.trap
AS
BEGIN
 SET NOCOUNT ON;
 DECLARE @scratch TABLE(n int); INSERT @scratch VALUES(1); SELECT CONVERT(varchar(20),COUNT(*)) AS value FROM @scratch;
END;
GO
