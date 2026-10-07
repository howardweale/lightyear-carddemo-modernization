-- Authored public M0 trap; NOT natively qualified.
CREATE OR ALTER PROCEDURE dbo.trap
AS
BEGIN
 SET NOCOUNT ON;
  SELECT CONVERT(varchar(200), (SELECT COUNT(*) FROM (VALUES ('A'),('a')) a(v) JOIN (VALUES ('A')) b(v) ON a.v COLLATE Latin1_General_100_CI_AS=b.v)) AS value;
END;
GO
