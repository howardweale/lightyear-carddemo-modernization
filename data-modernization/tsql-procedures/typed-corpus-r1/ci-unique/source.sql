-- Authored public M0 trap; NOT natively qualified.
CREATE OR ALTER PROCEDURE dbo.trap_ci_unique @input_value varchar(200)
AS
BEGIN
 SET NOCOUNT ON;
 INSERT dbo.names(v) VALUES (@input_value); BEGIN TRY INSERT dbo.names(v) VALUES ('a'); END TRY BEGIN CATCH IF ERROR_NUMBER() NOT IN (2601,2627) THROW; END CATCH; SELECT CONVERT(varchar(20),COUNT(*)) AS value FROM dbo.names;
END;
GO
