-- Authored public M0 trap; NOT natively qualified.
CREATE OR ALTER PROCEDURE dbo.trap @answer int OUTPUT
AS
BEGIN
 SET NOCOUNT ON;
 SET @answer=7;
END;
GO
