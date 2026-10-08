CREATE SCHEMA IF NOT EXISTS dbo;
CREATE TABLE dbo.effects(id integer PRIMARY KEY, amount integer NOT NULL);
CREATE FUNCTION dbo.rollback_probe() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'public rollback coverage case' USING ERRCODE='22012'; END; $$; CREATE TRIGGER rollback_probe BEFORE INSERT ON dbo.effects FOR EACH ROW EXECUTE FUNCTION dbo.rollback_probe();
