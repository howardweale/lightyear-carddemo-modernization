-- Authored public M0 trap; NOT natively qualified.
CREATE OR ALTER PROCEDURE dbo.trap_set_trigger @arg_amount int
AS
BEGIN
 SET NOCOUNT ON;
 INSERT dbo.effects VALUES(1,@arg_amount),(2,20); SELECT CONVERT(varchar(20),COUNT(*)) AS value FROM dbo.audit;
END;
GO
