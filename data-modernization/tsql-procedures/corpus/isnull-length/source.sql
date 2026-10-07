-- Authored public M0 trap; NOT natively qualified.
CREATE OR ALTER PROCEDURE dbo.trap
AS
BEGIN
 SET NOCOUNT ON;
  SELECT CONVERT(varchar(200), (ISNULL(CAST(NULL AS varchar(3)),'abcdef'))) AS value;
END;
GO
