-- Authored public M0 trap; NOT natively qualified.
CREATE OR ALTER PROCEDURE dbo.trap
AS
BEGIN
 SET NOCOUNT ON;
 SELECT v AS value FROM (VALUES (CAST(NULL AS varchar(10))),('a'),('B')) t(v) ORDER BY v COLLATE Latin1_General_100_CI_AS;
END;
GO
