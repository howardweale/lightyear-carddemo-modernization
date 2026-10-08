-- Authored public M0 trap; NOT natively qualified.
CREATE OR ALTER PROCEDURE dbo.trap_convert_style @day_value date
AS
BEGIN
 SET NOCOUNT ON;
  SELECT CONVERT(varchar(200), (CONVERT(varchar(10),CAST(@day_value AS date),103))) AS value;
END;
GO
