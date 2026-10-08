-- Authored public M0 trap; NOT natively qualified.
CREATE OR ALTER PROCEDURE dbo.trap_empty_int @input_value varchar(200)
AS
BEGIN
 SET NOCOUNT ON;
  SELECT CONVERT(varchar(200), (CAST(@input_value AS int))) AS value;
END;
GO
