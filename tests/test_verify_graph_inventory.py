"""CI-only full inventory and decoded protected-value regressions."""
import base64
import copy
import unittest
from lightyear_factory.contracts import ContractError
from lightyear_toolkit.graph_inventory import scan_inventory

class GraphInventoryTests(unittest.TestCase):
    def test_every_surface_and_decoded_source_are_scanned(self):
        canaries = {k: k + "-" + "x" * 40 for k in
                    ("expected-state", "reference-output", "session-answer")}
        payload = {"nodes": [{"id": "public", "source": [{"text": "public source"}]}],
                   "edges": [{"source": "public", "target": "public"}],
                   "annotations": [{"text": "public guidance"}],
                   "extension": {"text": "public metadata"}}
        token = "hidden-expected-" + "z" * 40
        def run(p):
            return scan_inventory(p, canaries=canaries, protected_values=[token, "Q12345678"],
                                  projection_sha256="a" * 64)
        with self.assertRaisesRegex(ContractError, "isolation-breach"):
            run({**payload, "Q12345678": []})
        clean = run(payload)
        self.assertEqual(1, clean["source_excerpts"])
        self.assertEqual(1, clean["guidance_records"])
        self.assertEqual(4, clean["records_scanned"])
        for kind in ("node", "edge", "guidance", "extension", "source"):
            for value in (token, base64.b64encode(token.encode()).decode(),
                          "Q12345678", "q 1 2 3 4 5 6 7 8",
                          base64.b64encode(("Q12345678" * 2).encode()).decode()):
                with self.subTest(kind=kind, encoding=value[:10]):
                    p = copy.deepcopy(payload)
                    if kind == "source":
                        p["nodes"][0]["source"][0]["text"] = value
                    elif kind == "node":
                        p["nodes"][0]["id"] = value
                    elif kind == "edge":
                        p["edges"][0]["target"] = value
                    elif kind == "guidance":
                        p["annotations"][0]["text"] = value
                    else:
                        p["extension"]["text"] = value
                    with self.assertRaisesRegex(ContractError, "isolation-breach"):
                        run(p)

    def test_canary_and_limits_fail_closed_without_echo(self):
        canaries = {k: k + "-" + "x" * 40 for k in
                    ("expected-state", "reference-output", "session-answer")}
        for value in canaries.values():
            with self.assertRaisesRegex(ContractError, "^isolation-breach$"):
                scan_inventory({"nodes": [{"source": [{"text": value}]}], "edges": []},
                               canaries=canaries, protected_values=[], projection_sha256="a"*64)
        with self.assertRaisesRegex(ContractError, "isolation-scan-limit"):
            scan_inventory({"nodes": [{"source": ["x" * (8*1024*1024+1)]}], "edges": []},
                           canaries=canaries, protected_values=[], projection_sha256="a"*64)
