"""Real test-Tower signatures, with no production keys or workload execution."""
import copy
import hashlib
import json
import unittest

from tests import test_decision_console_factory as fixtures
from lightyear_control_tower.factory_policy import FactoryDecisions, validate_contract, write_request
from lightyear_control_tower.threshold_conditions import DECISIONS, REPOSITORY, condition_hashes


class ThresholdConditionTests(unittest.TestCase):
    setUp = fixtures.FactoryTests.setUp
    contract = fixtures.FactoryTests.contract
    decide = fixtures.FactoryTests.decide
    def threshold(self):
        c = self.contract("scenario-threshold-approval")
        raw = (REPOSITORY / DECISIONS).read_bytes()
        (self.root / DECISIONS).write_bytes(raw)
        evidence = dict(path=DECISIONS, sha256=hashlib.sha256(raw).hexdigest(), commit="b"*40)
        c["sources"].append(evidence)
        c["details"].update(effective_condition="unconditional", conditions=[
            dict(condition_sha256=h, state="met", evidence=copy.deepcopy(evidence))
            for h in sorted(condition_hashes())])
        return c

    def test_unmet_or_omitted_condition_refused_before_signing(self):
        for mode in ("unmet", "missing", "empty", "duplicate", "legacy"):
            c = self.threshold()
            rows = c["details"]["conditions"]
            if mode == "unmet": rows[0].update(state="not-met", evidence=None)
            if mode == "missing": rows.pop()
            if mode == "empty": rows.clear()
            if mode == "duplicate": rows[-1] = copy.deepcopy(rows[0])
            if mode == "legacy": del c["details"]["conditions"]
            with self.subTest(mode=mode), self.assertRaisesRegex(ValueError, "threshold-conditions-unmet"):
                write_request(self.root, c)

    def test_changed_hash_and_forged_source_refused(self):
        for mode in ("hash", "source", "bytes", "commit"):
            c = self.threshold()
            if mode == "hash": c["details"]["conditions"][0]["evidence"]["sha256"] = "f"*64
            if mode == "source":
                c["sources"][-1]["sha256"] = "f"*64
                for row in c["details"]["conditions"]: row["evidence"]["sha256"] = "f"*64
            if mode == "bytes": (self.root / DECISIONS).write_text("changed")
            if mode == "commit": c["details"]["conditions"][0]["evidence"]["commit"] = "f"*40
            with self.subTest(mode=mode), self.assertRaisesRegex(ValueError, "threshold-conditions-unmet"):
                validate_contract(c, self.root)

    def test_fully_met_fixture_signs_and_changed_evidence_cannot_be_consumed(self):
        c = self.threshold()
        proof, _, _ = self.decide(c)
        reader = FactoryDecisions(self.service.public_key, proof["journal"]["journal_head_sha256"], evidence_root=self.root)
        reader.verify(proof, c["kind"], c, ("approve",))
        (self.root / DECISIONS).write_text("changed after signing")
        with self.assertRaisesRegex(ValueError, "threshold-conditions-unmet"):
            reader.verify(proof, c["kind"], c, ("approve",))

    def test_regenerated_request_is_not_signable_and_history_is_preserved(self):
        for date in ("2026-10-14", "2026-10-15"):
            c = json.loads((REPOSITORY / f"docs/factory/scenario-threshold-effective-request-{date}.json").read_bytes())
            with self.assertRaisesRegex(ValueError, "threshold-conditions-unmet"):
                validate_contract(c)
