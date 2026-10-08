-- Authored public M0 trap; NOT natively qualified.
CREATE OR ALTER PROCEDURE dbo.trap_nested_transaction_rollback @arg_amount int
AS
BEGIN
 SET NOCOUNT ON;
 BEGIN TRAN; INSERT dbo.effects VALUES(1,@arg_amount); BEGIN TRAN; INSERT dbo.effects VALUES(2,20); COMMIT; ROLLBACK; SELECT CONVERT(varchar(20),COUNT(*)) AS value FROM dbo.effects;
END;
GO
