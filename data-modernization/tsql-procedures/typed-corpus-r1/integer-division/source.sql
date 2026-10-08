-- Authored public M0 trap; NOT natively qualified.
CREATE OR ALTER PROCEDURE dbo.trap_integer_division @lhs int,@rhs int
AS
BEGIN
 SET NOCOUNT ON;
 SELECT CONVERT(varchar(200),@lhs/@rhs) AS value;
END;
GO
