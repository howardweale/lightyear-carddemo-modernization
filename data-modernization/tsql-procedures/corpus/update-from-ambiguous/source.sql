-- Authored public M0 trap; NOT natively qualified.
CREATE OR ALTER PROCEDURE dbo.trap
AS
BEGIN
 SET NOCOUNT ON;
 UPDATE e SET amount=m.v FROM dbo.effects e JOIN dbo.matches m ON e.id=m.k; SELECT CONVERT(varchar(20),amount) AS value FROM dbo.effects;
END;
GO
