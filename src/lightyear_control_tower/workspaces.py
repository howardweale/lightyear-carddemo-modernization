"""Single-customer deployment, disclosure projections and offline release proofs."""

import hashlib
from pathlib import Path
from .decisions import (
    DecisionUnauthorized,
    DecisionConflict,
    canonical,
    verify_envelope,
)
from .requests import read_json, confined
from .verification import verify_decision, verify_journal, check


def verify_export(archive, key, *, scope=None):
    check(
        archive.get("schema") == "tower-released-export/1"
        and verify_envelope(archive, key),
        "invalid-export-signature",
    )
    scope = scope or archive["scope"]
    check(archive["scope"] == scope, "export-scope-mismatch")
    bundle = archive["bundle"]
    raw = canonical(bundle)
    check(
        bundle.get("schema") == "tower-evidence-bundle/1"
        and bundle.get("scope") == scope,
        "bundle-scope-mismatch",
    )
    check(bundle.get("disclosure") == "public-evidence", "bundle-disclosure-refused")
    check(
        hashlib.sha256(raw).hexdigest() == archive["archive_sha256"],
        "archive-hash-mismatch",
    )
    check(verify_envelope(bundle, key), "bundle-signature-invalid")
    role_actors = {}
    for role in ("customer-sponsor", "campaign-authorizer"):
        proof = archive["release_decisions"][role]
        p = verify_decision(
            proof,
            key,
            "evidence-release",
            archive["release_bound"],
            scope=scope,
            expected_head=archive["decision_head_sha256"],
            outcomes=("approved",),
        )
        check(
            p.get("decision_slot") == role and role in p["roles_held"],
            "release-role-mismatch",
        )
        if role == "customer-sponsor":
            check(p["actor"]["kind"] == "customer", "customer-identity-required")
        role_actors[role] = p["actor"]["id"]
    check(len(set(role_actors.values())) == 2, "two-release-identities-required")
    check(
        archive["release_bound"]["archive"] == archive["archive_sha256"],
        "release-archive-mismatch",
    )
    kinds = set()
    for member in bundle["members"]:
        check(member["scope"] == scope, "member-scope-mismatch")
        check(
            member["kind"]
            in {"receipt", "journal", "rule-register", "catalogue-entry"},
            "unsupported-export-member",
        )
        value = member["record"]
        check(
            member["sha256"] == hashlib.sha256(canonical(value)).hexdigest(),
            "member-hash-mismatch",
        )
        if member["kind"] == "journal":
            verify_journal(value, key, scope=scope)
        else:
            check(
                verify_envelope(value, key) and value.get("scope") == scope,
                "member-signature-or-scope-invalid",
            )
        kinds.add(member["kind"])
    check(
        {"receipt", "journal", "rule-register", "catalogue-entry"} <= kinds,
        "incomplete-evidence-bundle",
    )
    return {
        "status": "verified",
        "scope": scope,
        "members": len(bundle["members"]),
        "archive_sha256": archive["archive_sha256"],
        "replay": "signatures, chains, scope, membership and dual release at archived head",
        "native_execution_repeated": False,
        "signature_type": "Service countersignature of authenticated operator intent",
    }


class Workspace:
    def __init__(self, service):
        self.service = service
        service.validators["evidence-release"] = self.validate_release

    def config(self):
        p = self.service.root / "control-tower/workspace.json"
        if not p.exists():
            return {"scope": self.service.scope, "configured": False}
        config = read_json(p)
        if config.get("scope") != self.service.scope:
            raise DecisionUnauthorized("Wrong workspace scope")
        return config

    def _record(self, relative):
        record = read_json(confined(self.service.root, relative))
        if record.get("scope") != self.service.scope:
            raise DecisionUnauthorized("Wrong evidence scope")
        if not verify_envelope(record, self.service.public_key):
            raise DecisionConflict("Workspace evidence signature invalid")
        return record

    def validate_release(self, item, payload, events, session):
        if payload["outcome"] == "rejected":
            return
        if (
            payload.get("decision_slot") == "customer-sponsor"
            and session["actor"]["kind"] != "customer"
        ):
            raise DecisionUnauthorized("Customer identity required")
        bundle = self._record(item["evidence"]["archive"])
        if bundle.get("schema") != "tower-evidence-bundle/1":
            raise DecisionConflict("Bound archive has wrong type")
        if bundle.get("disclosure") != "public-evidence":
            raise DecisionConflict("Archive must be a curated public-evidence bundle")
        # Canonical bytes are the exact released artifact, no ZIP traversal/extract.
        if hashlib.sha256(canonical(bundle)).hexdigest() != item["bound"]["archive"]:
            raise DecisionConflict("Evidence bundle must use canonical bytes")
        if not bundle.get("members"):
            raise DecisionConflict("Evidence archive is empty")
        kinds = set()
        for member in bundle["members"]:
            kind = member.get("kind")
            record = member.get("record", {})
            if member.get("scope") != self.service.scope or kind not in {
                "receipt",
                "journal",
                "rule-register",
                "catalogue-entry",
            }:
                raise DecisionConflict("Unapproved archive member")
            if member.get("sha256") != hashlib.sha256(canonical(record)).hexdigest():
                raise DecisionConflict("Member hash invalid")
            if kind == "journal":
                verify_journal(
                    record, self.service.public_key, scope=self.service.scope
                )
            elif record.get("scope") != self.service.scope or not verify_envelope(
                record, self.service.public_key
            ):
                raise DecisionConflict("Member signature or scope invalid")
            kinds.add(kind)
        if not {"receipt", "journal", "rule-register", "catalogue-entry"} <= kinds:
            raise DecisionConflict("Incomplete archive")

    def export(self, token, item_id):
        self.service._read_access(token)
        item = self.service.inbox.item(item_id)
        if item["kind"] != "evidence-release":
            raise ValueError("Not a release request")
        journal = self.service.export_session(token)
        events = journal["events"]
        decisions = {}
        for role in ("customer-sponsor", "campaign-authorizer"):
            e = self.service._latest(events, item, role)
            if not e:
                raise DecisionUnauthorized("Both release decisions are required")
            decisions[role] = {
                "schema": "tower-decision-proof/1",
                "decision_sha256": e["content_sha256"],
                "journal": journal,
            }
        result = self.service.sign(
            {
                "schema": "tower-released-export/1",
                "scope": self.service.scope,
                "bundle": self._record(item["evidence"]["archive"]),
                "archive_sha256": item["bound"]["archive"],
                "release_bound": item["bound"],
                "release_decisions": decisions,
                "decision_head_sha256": journal["journal_head_sha256"],
                "README": "Offline: python -m lightyear_control_tower verify-export --archive export.json --trusted-public-key trusted.pem. "
                "Verifies archived evidence and decisions; does not re-execute native workloads.",
                "signature_type": "Service countersignature of authenticated operator intent",
            }
        )
        verify_export(result, self.service.public_key, scope=self.service.scope)
        return result

    def view(self, token):
        session = self.service.authenticate(token)
        if not session["roles"]:
            raise DecisionUnauthorized("A scoped role is required")
        cfg = self.config()
        if not cfg.get("configured", True):
            return {"scope": self.service.scope, "configured": False}
        snapshot = self._record(cfg["snapshot"])
        # Field allowlists, not arbitrary captures or estate attributes. Disclosure
        # defaults to no values even for operators; archive members are curated.
        base = {
            "scope": self.service.scope,
            "configured": True,
            "title": cfg.get("title", self.service.scope),
            "slice": snapshot.get("slice", {}),
            "progress": snapshot.get("progress", {}),
            "verdicts": [
                {k: r[k] for k in ("id", "verdict", "receipt_sha256") if k in r}
                for r in snapshot.get("verdicts", [])
            ],
        }
        base["counts"] = {
            v: sum(r.get("verdict") == v for r in base["verdicts"])
            for v in ("equivalent", "divergent", "indeterminate")
        }
        partner = "partner-viewer" in session["roles"]
        level = "operator"
        if partner:
            with self.service.transaction() as db:
                shares = [
                    e
                    for e in self.service.events(db)
                    if e["kind"] == "tower_decision"
                    and e["payload"]["kind"] == "partner-share"
                ]
            level = "none"
            if shares:
                p = shares[-1]["payload"]
                item = self.service.inbox.item(p["item_id"])
                if p["bound"] == item["bound"]:
                    terms = read_json(
                        confined(self.service.root, item["evidence"]["share"])
                    )
                    if (
                        terms.get("partner_id") == session["actor"]["id"]
                        and terms.get("scope") == self.service.scope
                    ):
                        level = p["outcome"]
            if level == "none":
                return {
                    "scope": self.service.scope,
                    "shared_level": "none",
                    "configured": True,
                }
        if level in {"summary", "evidence", "operator"}:
            base["differences"] = [
                {k: r[k] for k in ("id", "class") if k in r}
                for r in snapshot.get("differences", [])
            ]
            base["rules"] = [
                {k: r[k] for k in ("id", "title") if k in r}
                for r in snapshot.get("rules", [])
            ]
        if not partner:
            base["estate"] = [
                {
                    k: r[k]
                    for k in ("id", "kind", "name", "lane", "catalogue_status")
                    if k in r
                }
                for r in snapshot.get("estate", [])
            ]
        base["shared_level"] = level
        if level == "evidence":
            # Already released offline artifact. Verify again on every read.
            released = self._record(cfg["released_archive"])
            verify_export(released, self.service.public_key, scope=self.service.scope)
            base["released_archive_sha256"] = released["archive_sha256"]
            # Partners see no raw members, traces, journal notes or values.
            if terms.get("archive_sha256") != released["archive_sha256"]:
                raise DecisionUnauthorized(
                    "Customer share does not bind this released archive"
                )
            base["evidence"] = released
        return base
