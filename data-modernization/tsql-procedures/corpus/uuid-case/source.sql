-- Authored public M0 trap; NOT natively qualified.
CREATE OR ALTER PROCEDURE dbo.trap
AS
BEGIN
 SET NOCOUNT ON;
  SELECT CONVERT(varchar(200), (LOWER(CONVERT(varchar(36),CAST('A0B1C2D3-E4F5-4678-9012-123456789ABC' AS uniqueidentifier))))) AS value;
END;
GO
