-- Authored public M0 trap; NOT natively qualified.
CREATE OR ALTER PROCEDURE dbo.trap_null_and_collation_order @input_value varchar(200)
AS
BEGIN
 SET NOCOUNT ON;
 SELECT v AS value FROM (VALUES (CAST(NULL AS varchar(10))),('a'),(@input_value)) t(v) ORDER BY v COLLATE Latin1_General_100_CI_AS;
END;
GO
