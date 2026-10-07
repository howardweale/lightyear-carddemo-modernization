-- Authored public M0 trap; NOT natively qualified.
CREATE OR ALTER PROCEDURE dbo.trap
AS
BEGIN
 SET NOCOUNT ON;
 DECLARE @out nvarchar(100); EXEC sp_executesql N'SELECT @r=@p',N'@p nvarchar(100),@r nvarchar(100) OUTPUT',@p=N'O''Brien',@r=@out OUTPUT; SELECT @out AS value;
END;
GO
