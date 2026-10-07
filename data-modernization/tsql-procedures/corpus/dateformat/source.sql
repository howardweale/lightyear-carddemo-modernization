-- Authored public M0 trap; NOT natively qualified.
CREATE OR ALTER PROCEDURE dbo.trap
AS
BEGIN
 SET NOCOUNT ON;
 SET DATEFORMAT dmy; SELECT CONVERT(varchar(200), (CONVERT(varchar(10),CAST('03/04/2026' AS date),23))) AS value;
END;
GO
