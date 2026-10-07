-- Authored public M0 trap; NOT natively qualified.
CREATE OR ALTER PROCEDURE dbo.trap
AS
BEGIN
 SET NOCOUNT ON;
 SET DATEFIRST 1; SELECT CONVERT(varchar(200), (DATEPART(weekday,CAST('20261004' AS date)))) AS value;
END;
GO
