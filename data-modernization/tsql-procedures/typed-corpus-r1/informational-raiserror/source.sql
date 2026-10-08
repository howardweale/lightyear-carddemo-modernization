-- Authored public M0 trap; NOT natively qualified.
CREATE OR ALTER PROCEDURE dbo.trap_informational_raiserror @input_value varchar(200)
AS
BEGIN
 SET NOCOUNT ON;
 RAISERROR(@input_value,10,1); SELECT 'done' AS value;
END;
GO
