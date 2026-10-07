-- Authored public M0 trap; NOT natively qualified.
CREATE OR ALTER PROCEDURE dbo.trap
AS
BEGIN
 SET NOCOUNT ON;
  SELECT CONVERT(varchar(200), (SELECT COUNT(DISTINCT v COLLATE Latin1_General_100_CI_AS) FROM (VALUES ('A'),('a')) x(v))) AS value;
END;
GO
