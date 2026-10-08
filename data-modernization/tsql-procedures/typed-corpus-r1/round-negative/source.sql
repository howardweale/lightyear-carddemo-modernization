-- Authored public M0 trap; NOT natively qualified.
CREATE OR ALTER PROCEDURE dbo.trap_round_negative @arg_amount int
AS
BEGIN
 SET NOCOUNT ON;
  SELECT CONVERT(varchar(200), (ROUND(CAST(@arg_amount AS decimal(6,0)),-2))) AS value;
END;
GO
