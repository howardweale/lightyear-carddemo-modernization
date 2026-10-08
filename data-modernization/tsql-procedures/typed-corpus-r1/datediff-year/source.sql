-- Authored public M0 trap; NOT natively qualified.
CREATE OR ALTER PROCEDURE dbo.trap_datediff_year @finish datetime2
AS
BEGIN
 SET NOCOUNT ON;
  SELECT CONVERT(varchar(200), (DATEDIFF(year,'20251231',@finish))) AS value;
END;
GO
