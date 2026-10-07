-- Authored public M0 trap; NOT natively qualified.
CREATE OR ALTER PROCEDURE dbo.trap
AS
BEGIN
 SET NOCOUNT ON;
  SELECT CONVERT(varchar(200), (ROUND(CAST(-150 AS decimal(6,0)),-2))) AS value;
END;
GO
