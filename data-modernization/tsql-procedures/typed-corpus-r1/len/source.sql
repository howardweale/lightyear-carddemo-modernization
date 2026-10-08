-- Authored public M0 trap; NOT natively qualified.
CREATE OR ALTER PROCEDURE dbo.trap_len @input_value varchar(200)
AS
BEGIN
 SET NOCOUNT ON;
  SELECT CONVERT(varchar(200), (LEN(@input_value))) AS value;
END;
GO
