-- Authored public M0 trap; NOT natively qualified.
CREATE OR ALTER PROCEDURE dbo.trap
AS
BEGIN
 SET NOCOUNT ON;
 RAISERROR('public informational message',10,1); SELECT 'done' AS value;
END;
GO
