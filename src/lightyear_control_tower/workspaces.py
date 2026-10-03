"""Single-customer deployment, disclosure projections and offline release proofs."""

import hashlib
import json
from pathlib import Path
from .decisions import (
    DecisionUnauthorized,
    DecisionConflict,
    canonical,
    verify_envelope,
    ZERO,
    digest,
)
from .requests import read_json, confined
from .verification import verify_decision, verify_journal, check
from .presentation import workspace_status


def chain_prefix(events):
    # Commitments reveal no proposals, reasons, names or sessions.
    return [
        {k: e[k] for k in ("sequence", "previous_sha256", "content_sha256")}
        for e in events
    ]


def verify_prefix(rows):
    previous = ZERO
    for index, row in enumerate(rows, 1):
        check(
            set(row) == {"sequence", "previous_sha256", "content_sha256"},
            "prefix-disclosure-refused",
        )
        check(
            row["sequence"] == index and row["previous_sha256"] == previous,
            "broken-release-prefix",
        )
        previous = row["content_sha256"]
    return previous


def verify_export(archive, key, *, scope=None):
    if archive.get("schema") == "zos-released-export/1":
        from .carddemo_console import verify_release

        check(scope in (None, "carddemo-zos"), "scope-mismatch")
        return verify_release(archive, key)
    check(
        archive.get("schema") == "tower-released-export/2"
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
    context = bundle["release_proof"]["context"]
    check(
        bundle["release_proof"]["format"] == "release-only-with-chain-commitments/1",
        "release-proof-format-refused",
    )
    check(
        verify_envelope(context, key) and context.get("scope") == scope,
        "release-context-invalid",
    )
    check(
        verify_prefix(context["prefix"]) == context["head"],
        "release-context-head-mismatch",
    )
    prefix = archive["decision_prefix"]
    check(
        prefix[: len(context["prefix"])] == context["prefix"],
        "release-context-mismatch",
    )
    check(
        verify_prefix(prefix) == archive["decision_head_sha256"],
        "release-head-mismatch",
    )
    role_actors = {}
    for role in ("customer-sponsor", "campaign-authorizer"):
        event = archive["release_decisions"][role]
        check(
            verify_envelope(event, key) and event.get("kind") == "tower_decision",
            "release-decision-invalid",
        )
        check(event["sequence"] > len(context["prefix"]), "release-before-context")
        check(
            chain_prefix([event])[0] == prefix[event["sequence"] - 1],
            "release-chain-position-mismatch",
        )
        p = event["payload"]
        check(
            p.get("kind") == "evidence-release"
            and p.get("scope") == scope
            and p.get("bound") == archive["release_bound"]
            and p.get("outcome") == "approved"
            and p.get("actor") == event["actor"]
            and p.get("channel") == "control-tower"
            and p.get("session_id") == event["session_id"]
            and not {"agent", "auditor", "partner-viewer"}.intersection(
                p.get("roles_held", [])
            ),
            "release-decision-refused",
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
        max(e["sequence"] for e in archive["release_decisions"].values())
        == len(prefix),
        "release-prefix-exceeds-decisions",
    )
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
        service.finalizers["evidence-release"] = self.freeze_export
        with service.transaction() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS released_exports (release_key TEXT PRIMARY KEY, envelope TEXT NOT NULL)"
            )

    def prepare_bundle(self, members):
        with self.service.transaction() as db:
            events = self.service.events(db)
            context = self.service.sign(
                {
                    "schema": "tower-release-context/1",
                    "scope": self.service.scope,
                    "prefix": chain_prefix(events),
                    "head": events[-1]["content_sha256"] if events else ZERO,
                }
            )
        return self.service.sign(
            {
                "schema": "tower-evidence-bundle/1",
                "scope": self.service.scope,
                "disclosure": "public-evidence",
                "members": members,
                "release_proof": {
                    "format": "release-only-with-chain-commitments/1",
                    "context": context,
                },
            }
        )

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
        for role in ("customer-sponsor", "campaign-authorizer"):
            other = self.service._latest(events, item, role)
            if (
                role != payload.get("decision_slot")
                and other
                and other["actor"]["id"] == session["actor"]["id"]
                and other["payload"]["outcome"] == "approved"
            ):
                raise DecisionUnauthorized(
                    "Two different release identities are required"
                )
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
        contract = bundle.get("release_proof", {})
        context = contract.get("context", {})
        if (
            contract.get("format") != "release-only-with-chain-commitments/1"
            or not verify_envelope(context, self.service.public_key)
            or context.get("scope") != self.service.scope
            or context.get("prefix")
            != chain_prefix(events[: len(context.get("prefix", []))])
            or verify_prefix(context.get("prefix", [])) != context.get("head")
        ):
            raise DecisionConflict(
                "Archive must bind the reviewed release context and disclosure format"
            )
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
        item["_release_bundle"] = bundle

    def freeze_export(self, db, item, events):
        decisions = {
            role: self.service._latest(events, item, role)
            for role in ("customer-sponsor", "campaign-authorizer")
        }
        if not all(
            e
            and e["payload"]["outcome"] == "approved"
            and e["payload"]["bound"] == item["bound"]
            for e in decisions.values()
        ):
            return
        result = self.service.sign(
            {
                "schema": "tower-released-export/2",
                "scope": self.service.scope,
                "bundle": item["_release_bundle"],
                "archive_sha256": item["bound"]["archive"],
                "release_bound": item["bound"],
                "release_decisions": decisions,
                "decision_prefix": chain_prefix(events),
                "decision_head_sha256": events[-1]["content_sha256"],
                "README": "Verify the curated bundle, signed release decisions and countersigned chain commitments offline; private journal payloads are not included. No native execution or present-day authorization claim.",
            }
        )
        verify_export(result, self.service.public_key, scope=self.service.scope)
        key = digest({role: e["content_sha256"] for role, e in decisions.items()})
        db.execute(
            "INSERT INTO released_exports VALUES (?, ?)",
            (key, canonical(result).decode()),
        )

    def export(self, token, item_id):
        self.service._read_access(token)
        item = self.service.inbox.item(item_id)
        if item["kind"] != "evidence-release":
            raise ValueError("Not a release request")
        with self.service.transaction() as db:
            events = self.service.events(db)
            decisions = {
                role: self.service._latest(events, item, role)
                for role in ("customer-sponsor", "campaign-authorizer")
            }
            if not all(
                e
                and e["payload"]["outcome"] == "approved"
                and e["payload"]["bound"] == item["bound"]
                for e in decisions.values()
            ):
                raise DecisionUnauthorized(
                    "Both current release decisions are required"
                )
            key = digest({role: e["content_sha256"] for role, e in decisions.items()})
            row = db.execute(
                "SELECT envelope FROM released_exports WHERE release_key=?", (key,)
            ).fetchone()
        if row is None:
            raise DecisionConflict(
                "Frozen release is unavailable; legacy exports require fresh review"
            )
        result = json.loads(row[0])
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
            "slice": {
                k: v
                for k, v in snapshot.get("slice", {}).items()
                if k
                in {
                    "id",
                    "lane_pair",
                    "programs",
                    "journeys",
                    "clock_policy",
                    "budget",
                    "success_criteria",
                }
            },
            "progress": {
                k: v
                for k, v in snapshot.get("progress", {}).items()
                if k in {"state", "completed", "total"}
            },
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
                for share in reversed(shares):
                    p = share["payload"]
                    item = self.service.inbox.item(p["item_id"])
                    if p["bound"] != item["bound"]:
                        continue
                    terms = read_json(
                        confined(self.service.root, item["evidence"]["share"])
                    )
                    if (
                        terms.get("partner_id") == session["actor"]["id"]
                        and terms.get("scope") == self.service.scope
                    ):
                        level = p["outcome"]
                        break
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
        if partner and level == "status":
            base = workspace_status(base)
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
