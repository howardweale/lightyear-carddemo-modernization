-- Authored public M0 trap; NOT natively qualified.
CREATE OR ALTER PROCEDURE dbo.trap_multiple_result_sets @input_value varchar(200)
AS
BEGIN
 SET NOCOUNT ON;
 SELECT @input_value AS value; SELECT 'second' AS value;
END;
GO
