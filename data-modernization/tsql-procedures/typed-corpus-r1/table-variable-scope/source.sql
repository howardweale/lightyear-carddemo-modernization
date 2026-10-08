-- Authored public M0 trap; NOT natively qualified.
CREATE OR ALTER PROCEDURE dbo.trap_table_variable_scope @input_value int
AS
BEGIN
 SET NOCOUNT ON;
 DECLARE @scratch TABLE(n int); INSERT @scratch VALUES(@input_value); SELECT CONVERT(varchar(20),COUNT(*)) AS value FROM @scratch;
END;
GO
