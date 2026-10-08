-- Authored public M0 trap; NOT natively qualified.
CREATE OR ALTER PROCEDURE dbo.trap_output_parameter @answer int OUTPUT,@input_value int
AS
BEGIN
 SET NOCOUNT ON;
 SET @answer=@input_value;
END;
GO
