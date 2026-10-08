-- Authored public M0 trap; NOT natively qualified.
CREATE OR ALTER PROCEDURE dbo.trap_ci_join @input_value varchar(200)
AS
BEGIN
 SET NOCOUNT ON;
  SELECT CONVERT(varchar(200), (SELECT COUNT(*) FROM (VALUES (@input_value),('a')) a(v) JOIN (VALUES (@input_value)) b(v) ON a.v COLLATE Latin1_General_100_CI_AS=b.v)) AS value;
END;
GO
