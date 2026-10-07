-- Authored public M0 trap; NOT natively qualified.
CREATE OR ALTER PROCEDURE dbo.trap
AS
BEGIN
 SET NOCOUNT ON;
  SELECT CONVERT(varchar(200), (DATEDIFF(year,'20251231','20260101'))) AS value;
END;
GO
