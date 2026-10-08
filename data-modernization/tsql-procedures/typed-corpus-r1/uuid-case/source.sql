-- Authored public M0 trap; NOT natively qualified.
CREATE OR ALTER PROCEDURE dbo.trap_uuid_case @input_value varchar(200)
AS
BEGIN
 SET NOCOUNT ON;
  SELECT CONVERT(varchar(200), (LOWER(CONVERT(varchar(36),CAST(@input_value AS uniqueidentifier))))) AS value;
END;
GO
