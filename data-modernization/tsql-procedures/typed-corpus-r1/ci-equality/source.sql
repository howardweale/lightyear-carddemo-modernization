-- Authored public M0 trap; NOT natively qualified.
CREATE OR ALTER PROCEDURE dbo.trap_ci_equality @input_value varchar(200)
AS
BEGIN
 SET NOCOUNT ON;
  SELECT CONVERT(varchar(200), (CASE WHEN @input_value COLLATE Latin1_General_100_CI_AS = 'alpha' THEN 1 ELSE 0 END)) AS value;
END;
GO
