-- Authored public M0 trap; NOT natively qualified.
CREATE OR ALTER PROCEDURE dbo.trap_dynamic_parameter_binding @input_value nvarchar(100)
AS
BEGIN
 SET NOCOUNT ON;
 DECLARE @out nvarchar(100); EXEC sp_executesql N'SELECT @r=@p',N'@p nvarchar(100),@r nvarchar(100) OUTPUT',@p=@input_value,@r=@out OUTPUT; SELECT @out AS value;
END;
GO
