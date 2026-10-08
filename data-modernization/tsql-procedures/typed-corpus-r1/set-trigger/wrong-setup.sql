-- Authored public M0 trap; NOT natively qualified.
CREATE SCHEMA IF NOT EXISTS dbo;
CREATE TABLE dbo.effects(id integer PRIMARY KEY, amount integer NOT NULL);
CREATE TABLE dbo.audit(total integer); CREATE FUNCTION dbo.effects_audit() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN INSERT INTO dbo.audit(total) VALUES(NEW.amount); RETURN NEW; END; $$; CREATE TRIGGER effects_audit AFTER INSERT ON dbo.effects FOR EACH ROW EXECUTE FUNCTION dbo.effects_audit();
