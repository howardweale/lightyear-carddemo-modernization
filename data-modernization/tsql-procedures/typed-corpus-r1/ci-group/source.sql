-- Authored public M0 trap; NOT natively qualified.
CREATE OR ALTER PROCEDURE dbo.trap_ci_group @input_value varchar(200)
AS
BEGIN
 SET NOCOUNT ON;
  SELECT CONVERT(varchar(200), (SELECT COUNT(*) FROM (SELECT v COLLATE Latin1_General_100_CI_AS AS k FROM (VALUES (@input_value),('a')) x(v) GROUP BY v COLLATE Latin1_General_100_CI_AS) g)) AS value;
END;
GO
