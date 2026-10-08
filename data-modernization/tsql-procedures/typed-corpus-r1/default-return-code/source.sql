-- Authored public M0 trap; NOT natively qualified.
CREATE OR ALTER PROCEDURE dbo.trap_default_return_code @input_value int
AS
BEGIN
 SET NOCOUNT ON;
 DECLARE @n int=@input_value;
END;
GO
