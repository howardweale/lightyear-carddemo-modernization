-- Authored public M0 trap; NOT natively qualified.
CREATE OR ALTER PROCEDURE dbo.trap
AS
BEGIN
 SET NOCOUNT ON;
 SELECT 'first' AS value; SELECT 'second' AS value;
END;
GO
