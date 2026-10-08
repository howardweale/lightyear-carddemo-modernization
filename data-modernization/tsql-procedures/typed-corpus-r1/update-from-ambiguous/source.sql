-- Authored public M0 trap; NOT natively qualified.
CREATE OR ALTER PROCEDURE dbo.trap_update_from_ambiguous @match_id int
AS
BEGIN
 SET NOCOUNT ON;
 UPDATE e SET amount=m.v FROM dbo.effects e JOIN dbo.matches m ON e.id=m.k WHERE e.id=@match_id; SELECT CONVERT(varchar(20),amount) AS value FROM dbo.effects;
END;
GO
