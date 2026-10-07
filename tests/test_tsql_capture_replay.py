"""Mock driver and ephemeral-key tests. These are not native engine receipts."""
from copy import deepcopy
from dataclasses import asdict
from datetime import date
from decimal import Decimal
import base64
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from lightyear_control_tower.decisions import canonical, digest
from lightyear_data.contracts import canonical_bytes, seal
from lightyear_data.tsql_procedures.adapters import Observation
from lightyear_data.tsql_procedures.capture import (
    CaptureIncomplete, COLUMNS, IDENTITIES, KEYS, SEQUENCES, SEQUENCE_OWNER, TABLES,
    capture_state, identifier, json_key, query, scalar, state_changes,
)
from lightyear_data.tsql_procedures.replay import ReplayFailure, replay


class Cursor:
    def __init__(self, responses):
        self.responses = responses
        self.closed = False
    def execute(self, sql, parameters=()):
        self.rows = list(self.responses[(sql, tuple(parameters))])
        return self
    def fetchmany(self, count):
        # Short pages exercise the explicit EOF loop.
        n = min(count, 1)
        page, self.rows = self.rows[:n], self.rows[n:]
        return page
    def close(self):
        self.closed = True


class Connection:
    def __init__(self, responses):
        self.responses = responses
        self.cursors = []
    def cursor(self):
        cursor = Cursor(self.responses)
        self.cursors.append(cursor)
        return cursor


def connection(engine):
    q = identifier("dbo", engine) + "." + identifier("effects", engine)
    responses = {
        (TABLES[engine], ()): [("dbo", "effects")],
        (COLUMNS[engine], ("dbo", "effects")): [("id", "int"), ("value", "varchar")],
        (KEYS[engine], ("dbo", "effects")): [("id",)],
        ("SELECT " + identifier("id", engine) + "," + identifier("value", engine) + " FROM " + q, ()):
            [(1, "a "), (2, None)],
    }
    if engine == "sqlserver":
        responses[(IDENTITIES, ())] = [("dbo", "effects", "id", "2", "1", "1")]
    else:
        responses[(SEQUENCES, ())] = [("dbo", "effects_id_seq")]
        responses[('SELECT last_value,is_called FROM "dbo"."effects_id_seq"', ())] = [(2, True)]
        responses[(SEQUENCE_OWNER, ('dbo','effects_id_seq'))] = [('dbo','effects','id',1,1)]
    return Connection(responses)


def state(engine):
    return capture_state(connection(engine), engine)


def obs(before, after):
    return Observation(
        [], {}, 0, None, None, state_changes(before, after),
        {"outcome": "committed"}, [], [], [], .01, "unit-fixture", {}, None,
    )


def signed(body, key, public):
    value = {**body, "content_sha256": digest(body)}
    value["signature"] = {
        "algorithm": "Ed25519", "key_id": hashlib.sha256(public).hexdigest(),
        "value": base64.b64encode(key.sign(canonical(body))).decode(),
    }
    return value


class CaptureTests(unittest.TestCase):
    def test_lossless_scalars(self):
        self.assertEqual("1.2300", scalar(Decimal("1.2300"))["value"])
        self.assertEqual("abc ", scalar("abc "))
        self.assertIsNone(scalar(None))
        self.assertEqual("AAE=", scalar(b"\x00\x01")["value"])
        self.assertEqual("2026-10-07", scalar(date(2026,10,7))["value"])
        self.assertEqual(float(0.1).hex(), scalar(.1)["value"])

    def test_unknown_and_nonfinite_values_fail(self):
        for v in (object(), float("nan"), float("inf"), Decimal("NaN")):
            with self.subTest(v=type(v)), self.assertRaises(CaptureIncomplete):
                scalar(v)

    def test_identifiers_are_quoted_not_interpolated_bare(self):
        self.assertEqual("[a]]b]", identifier("a]b", "sqlserver"))
        self.assertEqual('"a""b"', identifier('a"b', "postgresql"))
        with self.assertRaises(CaptureIncomplete): identifier("\x00","postgresql")

    def test_both_catalogs_capture_rows_keys_and_identity(self):
        for engine in ("sqlserver", "postgresql"):
            c = connection(engine); value = capture_state(c, engine)
            self.assertEqual(1, len(value["tables"]))
            t = value["tables"][json_key(("dbo","effects"))]
            self.assertEqual(["id"], t["primary_key"])
            self.assertEqual([{"id":1,"value":"a "},{"id":2,"value":None}], t["rows"])
            self.assertTrue(value["identity_sequence_state"])
            self.assertTrue(all(c.closed for c in c.cursors))

    def test_truncation_fails_and_closes_cursor(self):
        c = Connection({("SELECT x",()): [(1,), (2,)]})
        with self.assertRaisesRegex(CaptureIncomplete,"row-limit"):
            query(c, "SELECT x", maximum_rows=1)
        self.assertTrue(c.cursors[0].closed)

    def test_pk_changes_recomputed(self):
        before = state("sqlserver"); after = deepcopy(before)
        name = before["table_inventory"][0]
        after["tables"][name]["rows"][0]["value"] = "changed"
        after = seal(after)
        self.assertEqual(1, len(state_changes(before, after)["tables"][name]["changed"]))

    def test_corrupt_state_cannot_replay(self):
        before = state("sqlserver"); after = deepcopy(before)
        after["identity_sequence_state"] = {}
        with self.assertRaisesRegex(CaptureIncomplete,"invalid-state"):
            state_changes(before, after)

    def test_new_trigger_table_is_visible(self):
        before = state("sqlserver"); after = deepcopy(before)
        after["tables"]["new-table"] = {"columns":[["id","int"]],"primary_key":["id"],"rows":[{"id":1}]}
        after["table_inventory"].append("new-table"); after=seal(after)
        self.assertEqual("schema-change",state_changes(before,after)["tables"]["new-table"]["kind"])


class ReplayTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.key = Ed25519PrivateKey.generate()
        self.public = self.key.public_key().public_bytes(serialization.Encoding.PEM,
                                                       serialization.PublicFormat.SubjectPublicKeyInfo)
        self.files = {}
        for lane, engine in (("source","sqlserver"),("target","postgresql")):
            before = state(engine); after = deepcopy(before)
            values = {"before":before,"after":after,"observation":asdict(obs(before,after))}
            for kind, value in values.items():
                path = self.root/(lane+"-"+kind+".json")
                raw = canonical_bytes(value); path.write_bytes(raw)
                self.files[path.name] = hashlib.sha256(raw).hexdigest()
        self.body = {"schema":"tsql-capture-manifest/1","files":self.files,
                     "model_calls":0,"trap_family":1}
        self.manifest = self.write_manifest()

    def tearDown(self):
        self.tmp.cleanup()

    def write_manifest(self):
        value = signed(self.body, self.key, self.public)
        (self.root/"manifest.json").write_bytes(canonical(value))
        return value

    def test_authenticates_and_recomputes_without_claiming_equivalence(self):
        result = replay(self.root,self.public,self.manifest["content_sha256"])
        self.assertTrue(result["signature_verified"])
        self.assertTrue(result["side_effects_recomputed"])
        self.assertEqual("insufficient-evidence",result["verdict"])
        self.assertEqual(0,result["database_calls"])
        self.assertFalse(result["coverage"]["eligible"])

    def test_wrong_key_or_manifest_hash_rejected(self):
        for key, sha in ((self.public,"0"*64),(b"bad",self.manifest["content_sha256"])):
            with self.subTest(sha=sha),self.assertRaises(ReplayFailure):
                replay(self.root,key,sha)

    def test_modified_capture_rejected(self):
        with (self.root/"source-before.json").open("ab") as stream: stream.write(b" ")
        with self.assertRaisesRegex(ReplayFailure,"file-changed"):
            replay(self.root,self.public,self.manifest["content_sha256"])

    def test_signed_observation_still_must_match_raw_captures(self):
        path=self.root/"source-observation.json"; value=json.loads(path.read_bytes())
        value["side_effects"]["identity_sequence_state"]={}
        raw=canonical_bytes(value);path.write_bytes(raw)
        self.files[path.name]=hashlib.sha256(raw).hexdigest()
        manifest=self.write_manifest()
        with self.assertRaisesRegex(ReplayFailure,"side-effect-replay"):
            replay(self.root,self.public,manifest["content_sha256"])

    def test_missing_or_extra_files_rejected(self):
        (self.root/"unlisted.txt").write_text("not admitted")
        with self.assertRaisesRegex(ReplayFailure,"unlisted"):
            replay(self.root,self.public,self.manifest["content_sha256"])

    def test_path_injection_manifest_rejected(self):
        self.body["files"]={"../outside.json":"0"*64}
        manifest=self.write_manifest()
        with self.assertRaisesRegex(ReplayFailure,"file-closure"):
            replay(self.root,self.public,manifest["content_sha256"])

    def test_duplicate_json_key_rejected(self):
        path=self.root/"source-after.json"; raw=b'{"a":1,"a":2}'
        path.write_bytes(raw);self.files[path.name]=hashlib.sha256(raw).hexdigest()
        manifest=self.write_manifest()
        with self.assertRaisesRegex(ReplayFailure,"duplicate-json"):
            replay(self.root,self.public,manifest["content_sha256"])


if __name__=="__main__": unittest.main()
