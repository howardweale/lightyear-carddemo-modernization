-- Authored public M0 trap; NOT natively qualified.
CREATE OR ALTER PROCEDURE dbo.trap
AS
BEGIN
 SET NOCOUNT ON;
 SET XACT_ABORT ON; BEGIN TRY BEGIN TRAN; INSERT dbo.effects VALUES(1,10); DECLARE @zero int=0,@unused int; SET @unused=1/@zero; COMMIT; END TRY BEGIN CATCH IF @@TRANCOUNT>0 ROLLBACK; END CATCH; SELECT CONVERT(varchar(20),COUNT(*)) AS value FROM dbo.effects;
END;
GO
