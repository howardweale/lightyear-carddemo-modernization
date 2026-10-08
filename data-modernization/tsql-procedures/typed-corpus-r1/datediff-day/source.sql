-- Authored public M0 trap; NOT natively qualified.
CREATE OR ALTER PROCEDURE dbo.trap_datediff_day @finish datetime2
AS
BEGIN
 SET NOCOUNT ON;
  SELECT CONVERT(varchar(200), (DATEDIFF(day,'20261001 23:59:59',@finish))) AS value;
END;
GO
