-- Authored public M0 trap; NOT natively qualified.
CREATE OR ALTER PROCEDURE dbo.trap_trailing_varchar @input_value varchar(200)
AS
BEGIN
 SET NOCOUNT ON;
  SELECT CONVERT(varchar(200), (CASE WHEN CAST(@input_value AS varchar(3))=CAST('A' AS varchar(3)) THEN 1 ELSE 0 END)) AS value;
END;
GO
