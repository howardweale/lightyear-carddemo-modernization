-- Authored public M0 trap; NOT natively qualified.
CREATE OR ALTER PROCEDURE dbo.trap_datetime_002 @milliseconds int
AS
BEGIN
 SET NOCOUNT ON;
  SELECT CONVERT(varchar(200), (CONVERT(varchar(23),CAST(DATEADD(millisecond,@milliseconds,CAST('2026-10-01' AS datetime2)) AS datetime),121))) AS value;
END;
GO
