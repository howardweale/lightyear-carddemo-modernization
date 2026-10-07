-- Authored public M0 trap; NOT natively qualified.
CREATE OR ALTER PROCEDURE dbo.trap
AS
BEGIN
 SET NOCOUNT ON;
 INSERT dbo.effects VALUES(1,10); BEGIN TRY DECLARE @zero int=0; DECLARE @unused int; SET @unused=1/@zero; END TRY BEGIN CATCH INSERT dbo.effects VALUES(2,20); END CATCH; SELECT CONVERT(varchar(20),COUNT(*)) AS value FROM dbo.effects;
END;
GO
