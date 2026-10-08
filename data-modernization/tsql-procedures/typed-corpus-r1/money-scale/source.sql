-- Authored public M0 trap; NOT natively qualified.
CREATE OR ALTER PROCEDURE dbo.trap_money_scale @arg_amount decimal(10,5)
AS
BEGIN
 SET NOCOUNT ON;
  SELECT CONVERT(varchar(200), (CONVERT(varchar(30),CAST(@arg_amount AS money),2))) AS value;
END;
GO
