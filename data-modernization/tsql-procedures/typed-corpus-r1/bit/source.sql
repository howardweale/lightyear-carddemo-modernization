-- Authored public M0 trap; NOT natively qualified.
CREATE OR ALTER PROCEDURE dbo.trap_bit @input_value int
AS
BEGIN
 SET NOCOUNT ON;
  SELECT CONVERT(varchar(200), (CAST(@input_value AS bit))) AS value;
END;
GO
