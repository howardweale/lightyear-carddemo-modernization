"""CI-only graph retention rejects malformed archives and crossed bindings."""
import copy
import io
import json
import stat
import unittest
import zipfile
from tools.ci.verify_graph_retention import payload, sha, validate_run, REPO

class GraphRetentionTests(unittest.TestCase):
    def fixture(self):
        run = dict(id=7, run_attempt=2, head_sha="a"*40, path=".github/workflows/lightyear-verify-mcp.yml",
                   status="completed", conclusion="success", event="pull_request",
                   repository=dict(full_name=REPO, private=False), head_repository=dict(full_name=REPO))
        encode = lambda v: json.dumps(v, sort_keys=True).encode()
        proof = encode({"fixture": True})
        scan = dict(schema="verify-graph-inventory-scan/1", status="passed",
                    all_projection_members_scanned=True, short_protected_values_scanned=True,
                    nodes=3, source_excerpts=3, authority="ephemeral-CI-fixture", projection_sha256="b"*64)
        scan_raw = encode(scan)
        report = dict(schema="verify-graph-on-acceptance/1", status="passed", commit=run["head_sha"],
                      run_id="7", run_attempt="2", authority="ephemeral-CI-fixture", live_activation=False,
                      tools_exercised=16, actual_native_submissions=5, offline_replays=5, model_calls=0,
                      projection_sha256="b"*64, approval_proof_sha256=sha(proof), leak_scan_sha256=sha(scan_raw))
        report_raw = encode(report)
        request = dict(schema="verify-graph-activation-preparation/1", unsigned=True, importable=False,
                       activation_authorized=False, approval_scope="ephemeral-CI-fixture-only",
                       remaining=["operator proof"], acceptance_sha256=sha(report_raw),
                       **{k: report[k] for k in ("commit","run_id","run_attempt","projection_sha256",
                                                 "approval_proof_sha256","leak_scan_sha256")})
        files = {"ci-fixture-approval-proof.json": proof, "graph-inventory-scan-2026-10-21T000000Z.json": scan_raw,
                 "graph-on-acceptance.json": report_raw, "unsigned-activation-preparation.json": encode(request)}
        return run, files

    def check(self, run, files, *, extra=None, symlink=False):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            for name, raw in files.items():
                info = zipfile.ZipInfo(name)
                info.external_attr = ((stat.S_IFLNK if symlink else stat.S_IFREG) | 0o644) << 16
                z.writestr(info, raw)
            if extra:
                z.writestr(*extra)
        raw = buf.getvalue()
        return payload(raw, dict(size_in_bytes=len(raw), digest="sha256:"+sha(raw)), run)

    def test_valid_fixture_cross_bindings_and_archive_closure(self):
        run, files = self.fixture()
        validate_run(run)
        self.assertEqual(files, self.check(run, files))
        for key, value in (("head_sha","f"*40), ("run_attempt",3), ("id",8)):
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.check({**run, key:value}, files)
        with self.assertRaises(ValueError):
            self.check(run, files, extra=("../authority.pem", b"not public"))
        with self.assertRaises(ValueError):
            self.check(run, files, symlink=True)
        for name in files:
            bad = dict(files)
            if name == "unsigned-activation-preparation.json":
                body = json.loads(bad[name]); body["acceptance_sha256"] = "f"*64
                bad[name] = json.dumps(body).encode()
            else:
                bad[name] += b" "
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.check(run, bad)
        bad = copy.deepcopy(run);bad["head_repository"]["full_name"]="fork/other"
        with self.assertRaises(ValueError): validate_run(bad)

    def test_no_live_activation_and_no_incomplete_scan(self):
        run, files = self.fixture()
        for name, key, value in (
            ("unsigned-activation-preparation.json","activation_authorized",True),
            ("unsigned-activation-preparation.json","importable",True),
            ("graph-on-acceptance.json","tools_exercised",10),
            ("graph-inventory-scan-2026-10-21T000000Z.json","all_projection_members_scanned",False),
        ):
            changed=dict(files); body=json.loads(changed[name]);body[key]=value
            changed[name]=json.dumps(body).encode()
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.check(run, changed)
