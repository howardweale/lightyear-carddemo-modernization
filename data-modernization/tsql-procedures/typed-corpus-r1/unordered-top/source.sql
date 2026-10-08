-- Authored public M0 trap; NOT natively qualified.
CREATE OR ALTER PROCEDURE dbo.trap_unordered_top @input_value int
AS
BEGIN
 SET NOCOUNT ON;
  SELECT CONVERT(varchar(200), (SELECT TOP(1) v FROM (VALUES(1),(@input_value)) x(v))) AS value;
END;
GO
