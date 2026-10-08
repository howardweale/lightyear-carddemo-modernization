-- Authored public M0 trap; NOT natively qualified.
CREATE OR ALTER PROCEDURE dbo.calculate @lhs int,@rhs int
AS
BEGIN
 SET NOCOUNT ON;
 SELECT CONVERT(varchar(200),@lhs/@rhs) AS value;
END;
GO
