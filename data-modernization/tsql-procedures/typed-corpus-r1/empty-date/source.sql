-- Authored public M0 trap; NOT natively qualified.
CREATE OR ALTER PROCEDURE dbo.trap_empty_date @input_value varchar(200)
AS
BEGIN
 SET NOCOUNT ON;
  SELECT CONVERT(varchar(200), (CONVERT(varchar(10),CAST(@input_value AS datetime),23))) AS value;
END;
GO
