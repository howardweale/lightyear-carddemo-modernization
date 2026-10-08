-- Authored public M0 trap; NOT natively qualified.
CREATE OR ALTER PROCEDURE dbo.trap_datefirst @day_value date
AS
BEGIN
 SET NOCOUNT ON;
 SET DATEFIRST 1; SELECT CONVERT(varchar(200), (DATEPART(weekday,CAST(@day_value AS date)))) AS value;
END;
GO
