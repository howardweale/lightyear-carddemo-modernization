-- Authored public M0 trap; NOT natively qualified.
CREATE OR ALTER PROCEDURE dbo.trap_scope_identity_trigger @input_value int
AS
BEGIN
 SET NOCOUNT ON;
 INSERT dbo.items(v) VALUES(@input_value); SELECT CONVERT(varchar(20),CONVERT(int,SCOPE_IDENTITY())) AS value;
END;
GO
