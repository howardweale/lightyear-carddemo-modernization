-- Authored public M0 trap; NOT natively qualified.
CREATE OR ALTER PROCEDURE dbo.trap_isnull_length @input_value varchar(200)
AS
BEGIN
 SET NOCOUNT ON;
  SELECT CONVERT(varchar(200), (ISNULL(CAST(NULL AS varchar(3)),@input_value))) AS value;
END;
GO
