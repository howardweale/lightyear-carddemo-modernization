-- Authored public M0 trap; NOT natively qualified.
CREATE OR ALTER PROCEDURE dbo.trap_ci_distinct @input_value varchar(200)
AS
BEGIN
 SET NOCOUNT ON;
  SELECT CONVERT(varchar(200), (SELECT COUNT(DISTINCT v COLLATE Latin1_General_100_CI_AS) FROM (VALUES (@input_value),('a')) x(v))) AS value;
END;
GO
