-- Authored public M0 trap; NOT natively qualified.
CREATE OR ALTER PROCEDURE dbo.trap
AS
BEGIN
 SET NOCOUNT ON;
  SELECT CONVERT(varchar(200), (CONVERT(varchar(10),CAST('20260403' AS date),103))) AS value;
END;
GO
