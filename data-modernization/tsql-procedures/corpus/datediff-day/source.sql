-- Authored public M0 trap; NOT natively qualified.
CREATE OR ALTER PROCEDURE dbo.trap
AS
BEGIN
 SET NOCOUNT ON;
  SELECT CONVERT(varchar(200), (DATEDIFF(day,'20261001 23:59:59','20261002 00:00:00'))) AS value;
END;
GO
