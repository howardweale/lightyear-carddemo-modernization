"""Scoped decision kernel using the existing countersigned append-only journal.

No dispatch, subprocess, engine control, model client, or caller-supplied verdicts.
Legacy normalization consumers continue to use DecisionService unchanged.
"""

import hashlib
import json
import os
import secrets
import uuid
from datetime import date, timedelta
from pathlib import Path
from .decisions import (
    DecisionService,
    DecisionConflict,
    DecisionUnauthorized,
    canonical,
    digest,
    initialize_authority,
    text_field,
    utcnow,
    ZERO,
)
from .identity import LocalIdentityProvider
from .kinds import default_registry, ROLES, APPROVING_ROLES
from .requests import RequestInbox, identifier, read_json
from .presentation import evidence_view, age
from .proposals import proposal_actor
from .verification import subject
from .trust import qualification_key


def provision(path, scope, operator_id, name, *, identity_kind="human"):
    """New scoped authorities grant no roles; legacy init-operator stays compatible."""
    identifier(scope)
    if identity_kind not in {"human", "customer", "agent"}:
        raise ValueError("Unsupported identity kind")
    credential = initialize_authority(Path(path), operator_id, name)
    config = read_json(path)
    config["console_scope"] = scope
    config["operators"][0].update(roles=[], identity_kind=identity_kind)
    Path(path).write_bytes(canonical(config) + b"\n")
    return credential


class ConsoleService(DecisionService):
    def __new__(cls, root, authority, **kwargs):
        # Scope selection is authority-owned, never controlled by an HTTP request.
        if (
            cls is ConsoleService
            and read_json(authority).get("console_scope") == "carddemo-zos"
        ):
            from .carddemo_console import CarddemoConsole

            return object.__new__(CarddemoConsole)
        return object.__new__(cls)

    def __init__(self, root, authority, *, registry=None, identity_provider=None):
        config = read_json(authority)
        self.scope = identifier(config.get("console_scope"))
        root = Path(root).resolve()
        authority = Path(authority).resolve()
        if authority.is_relative_to(root):
            raise ValueError(
                "Console authority must be outside the engine-writable data root"
            )
        authority_files = [
            (authority.parent / config[field]).resolve()
            for field in ("private_key", "public_key")
        ] + [authority.with_suffix(".credential.txt").resolve()]
        if any(path.is_relative_to(root) for path in authority_files):
            raise ValueError(
                "Console keys and credentials must be outside the engine-writable data root"
            )
        # One engagement per data root. Two scopes/keys cannot accidentally share
        # files, journals or exports merely because a caller supplied another id.
        ownership = root / "work/control-tower/workspace-ownership.json"
        identity = {
            "scope": self.scope,
            "public_key_sha256": hashlib.sha256(
                (authority.parent / config["public_key"]).read_bytes()
            ).hexdigest(),
        }
        ownership.parent.mkdir(parents=True, exist_ok=True)
        if ownership.exists():
            if read_json(ownership) != identity:
                raise ValueError("Data root belongs to another scope or authority")
        else:
            with ownership.open("xb") as f:
                f.write(canonical(identity))
        self.registry = registry or default_registry()
        self.identity_provider = identity_provider or LocalIdentityProvider()
        super().__init__(
            Path(root),
            Path(authority),
            database=Path(root)
            / "work/control-tower/scopes"
            / self.scope
            / "decisions.sqlite3",
            decision_only=True,
        )
        self.inbox = RequestInbox(self.root, self.scope, self.registry)
        self.validators = (
            {}
        )  # Kind validators are installed by trusted application code.
        self.finalizers = {}

    def qualification_key(self):
        return qualification_key(
            self.root,
            self.authority_path.parent / "qualification-trust.json",
            scope=self.scope,
        )

    def dispatch(self, *args, **kwargs):
        raise DecisionUnauthorized("The Tower never dispatches work")

    def gate(self, *args, **kwargs):
        raise DecisionUnauthorized("The Tower never determines a verdict")

    def _roles(self, actor_id, events):
        # Scoped provision has no implicit roles. Only journaled explicit grants apply.
        latest = next(
            (
                e
                for e in reversed(events)
                if e["kind"] == "roles_assigned"
                and e["payload"].get("actor_id") == actor_id
                and e["payload"].get("scope") == self.scope
            ),
            None,
        )
        return latest["payload"]["roles"] if latest else []

    def grant_roles(self, actor_id, roles, *, reason, workloads=()):
        """Local administration only. Deliberately not exposed over HTTP or MCP."""
        reason = text_field(reason, "Role assignment reason")
        roles = sorted(set(roles))
        config = read_json(self.authority_path)
        person = next((o for o in config["operators"] if o["id"] == actor_id), None)
        if person is None or not set(roles) <= ROLES:
            raise ValueError("Unknown identity or role")
        if (person.get("identity_kind") == "agent" or "agent" in roles) and set(
            roles
        ) & APPROVING_ROLES:
            raise DecisionUnauthorized("Agents cannot hold approving roles")
        if "auditor" in roles and set(roles) - {"auditor"}:
            raise DecisionUnauthorized("Auditor credentials are read only")
        if "customer-sponsor" in roles and person.get("identity_kind") != "customer":
            raise DecisionUnauthorized("Sponsor must be a customer identity")
        with self.transaction() as db:
            return self.append(
                db,
                "roles_assigned",
                {
                    "scope": self.scope,
                    "actor_id": actor_id,
                    "roles": roles,
                    "workloads": sorted(set(workloads)),
                    "reason": reason,
                },
                {
                    "id": "local-authority-administrator",
                    "kind": "service",
                    "name": "Local authority administration",
                },
            )

    def add_identity(self, operator_id, name, *, identity_kind="human"):
        """Local-only provisioning. The returned secret is never journaled."""
        identifier(operator_id)
        if identity_kind not in {"human", "customer", "agent"}:
            raise ValueError("Unsupported identity kind")
        name = text_field(name, "Name", 200)
        token = secrets.token_urlsafe(48)
        with self.transaction() as db:
            config = read_json(self.authority_path)
            if any(o["id"] == operator_id for o in config["operators"]):
                raise ValueError("Identity already exists")
            config["operators"].append(
                {
                    "id": operator_id,
                    "name": name,
                    "identity_kind": identity_kind,
                    "roles": [],
                    "token_sha256": hashlib.sha256(token.encode()).hexdigest(),
                }
            )
            # Authority remains private. Update under the sole journal-writer lock.
            pending = self.authority_path.with_suffix(".pending")
            with pending.open("xb") as f:
                f.write(canonical(config) + b"\n")
            os.replace(pending, self.authority_path)
            self.append(
                db,
                "identity_provisioned",
                {
                    "scope": self.scope,
                    "actor_id": operator_id,
                    "identity_kind": identity_kind,
                    "roles": [],
                },
                self.system_actor(),
            )
        return token

    def login(self, credential):
        person = self.identity_provider.authenticate(
            credential, read_json(self.authority_path)["operators"]
        )
        token = secrets.token_urlsafe(32)
        with self.transaction() as db:
            session = {
                "id": str(uuid.uuid4()),
                "scope": self.scope,
                "actor": {
                    "id": person["id"],
                    "name": person["name"],
                    "kind": person.get("identity_kind", "human"),
                },
                "roles": self._roles(person["id"], self.events(db)),
                "authentication": self.identity_provider.authentication,
                "expires_at": (utcnow() + timedelta(hours=1)).isoformat(),
            }
            self.append(
                db,
                "session_started",
                {
                    "scope": self.scope,
                    "authentication": session["authentication"],
                    "expires_at": session["expires_at"],
                },
                session["actor"],
                session["id"],
            )
            self.sessions[token] = session
        return {**session, "token": token}

    def authenticate(self, token, role=None):
        session = super().authenticate(token)
        if session["scope"] != self.scope:
            raise DecisionUnauthorized("Wrong scope")
        with self.connect() as db:
            session = {
                **session,
                "roles": self._roles(session["actor"]["id"], self.events(db)),
            }
        if role and role not in session["roles"]:
            raise DecisionUnauthorized("Role required: " + role)
        return session

    def _deny(self, session, operation):
        with self.transaction() as db:
            self.append(
                db,
                "action_refused",
                {
                    "scope": self.scope,
                    "operation": operation,
                    "reason_code": "role-refused",
                },
                session["actor"],
                session["id"],
            )
        raise DecisionUnauthorized("This credential cannot perform this action")

    def _write_access(self, token, operation, roles=None, deciding=False):
        session = self.authenticate(token)
        held = set(session["roles"])
        if "auditor" in held or "partner-viewer" in held or not held:
            self._deny(session, operation)
        if deciding and (session["actor"]["kind"] == "agent" or "agent" in held):
            self._deny(session, operation)
        if roles and not held & set(roles):
            self._deny(session, operation)
        return session

    def _read_access(self, token):
        session = self.authenticate(token)
        if not session["roles"] or "partner-viewer" in session["roles"]:
            raise DecisionUnauthorized("Use the customer's shared view")
        return session

    @staticmethod
    def _latest(events, item, slot=None):
        return next(
            (
                e
                for e in reversed(events)
                if e["kind"] == "tower_decision"
                and e["payload"]["kind"] == item["kind"]
                and subject(item["kind"], e["payload"]["bound"])
                == subject(item["kind"], item["bound"])
                and e["payload"].get("decision_slot") == slot
            ),
            None,
        )

    def item(self, token, item_id):
        self._read_access(token)
        item = self.inbox.item(item_id)
        with self.transaction() as db:
            latest = self._latest(self.events(db), item)
        return {
            **item,
            "latest_decision": latest,
            "evidence_view": evidence_view(self.root, item),
            "signature_description": "Service countersignature of authenticated operator intent",
            "classification_item_ids": self.inbox.classification_ids(item),
        }

    def queue(self, token):
        session = self._read_access(token)
        inbox = self.inbox.queue()
        with self.connect() as db:
            events = self.events(db)
            items = []
            for item in inbox:
                if item["status"] != "invalid":
                    kind = self.registry.get(item["kind"])
                    latest = self._latest(events, item)
                    item = {
                        **item,
                        "required_roles": list(kind.roles),
                        "outcomes": list(kind.outcomes),
                        "age": age(item, kind.review_days),
                        "required_fields": list(kind.required_fields),
                        "latest_decision": latest,
                        "decidable": session["actor"]["kind"] != "agent"
                        and "agent" not in session["roles"]
                        and "auditor" not in session["roles"]
                        and bool(set(kind.roles) & set(session["roles"])),
                    }
                    if latest:
                        item["status"] = (
                            "decided"
                            if latest["payload"]["bound"] == item["bound"]
                            else "changed"
                        )
                        if (
                            item["kind"] == "difference-disposition"
                            and latest["payload"]["outcome"] == "intended-change"
                        ):
                            item["next_action"] = (
                                "typed-rule-proposal-required; verdict remains divergent"
                            )
                    if kind.independence == "required":
                        try:
                            author = proposal_actor(item, events)
                            item["proposed_by"] = author
                            if session["actor"]["id"] == author:
                                item.update(
                                    decidable=False,
                                    decision_refusal="independent-reviewer-required",
                                )
                        except ValueError:
                            item.update(
                                decidable=False,
                                decision_refusal="authenticated-proposal-required",
                            )
                items.append(item)
            return {
                "schema": "tower-queue/1",
                "scope": self.scope,
                "items": items,
                "session": session,
                "journal_head_sha256": events[-1]["content_sha256"] if events else ZERO,
                "supported_decisions": self.registry.names(),
            }

    def review(self, token, item_id):
        session = self._write_access(token, "review")
        item = self.inbox.item(item_id)
        view = evidence_view(self.root, item)
        classification_ids = self.inbox.classification_ids(item)
        with self.transaction() as db:
            latest = self._latest(self.events(db), item)
            self.append(
                db,
                "tower_item_viewed",
                {
                    "scope": self.scope,
                    "item_id": item["id"],
                    "bound": item["bound"],
                    "previous_decisions_by_role": {
                        role: (self._latest(self.events(db), item, role) or {}).get(
                            "content_sha256"
                        )
                        for role in self.registry.get(item["kind"]).roles
                    },
                    "previous_decision_sha256": (
                        latest["content_sha256"] if latest else None
                    ),
                },
                session["actor"],
                session["id"],
            )
            return {
                **item,
                "latest_decision": latest,
                "evidence_view": view,
                "classification_item_ids": classification_ids,
                "latest_decisions_by_role": {
                    role: (self._latest(self.events(db), item, role) or {}).get(
                        "content_sha256"
                    )
                    for role in self.registry.get(item["kind"]).roles
                },
            }

    def decide(self, token, payload):
        session = self._write_access(token, "decide", deciding=True)
        item = self.inbox.item(payload.get("item_id"))
        kind = self.registry.get(item["kind"])
        session = self._write_access(token, "decide", kind.roles, deciding=True)
        request_id = str(
            uuid.UUID(text_field(payload.get("request_id"), "Request ID", 36))
        )
        for field in kind.required_fields:
            text_field(payload.get(field), field)
        if payload.get("outcome") not in kind.outcomes:
            raise ValueError("Outcome is not allowed for this kind")
        if kind.name == "verify-graph-projection":
            from .graph_review import validate_approval
            validate_approval(self.root, item, payload)
        review_after = payload.get("review_after")
        if review_after and not utcnow().date() < date.fromisoformat(
            review_after
        ) <= utcnow().date() + timedelta(days=kind.max_review_days):
            raise ValueError(
                "Review date must be within the kind's maximum review interval"
            )
        # Release uses two distinct role slots, both bound to the same archive.
        slot = payload.get("decision_slot") if kind.name == "evidence-release" else None
        if kind.name == "evidence-release" and (
            slot not in kind.roles or slot not in session["roles"]
        ):
            raise DecisionUnauthorized("Choose a release role held by this identity")
        with self.connect() as db:
            prepared_events = self.events(db)
        proposer = item["proposed_by"]
        if kind.independence == "required":
            try:
                proposer = proposal_actor(item, prepared_events)
            except ValueError as exc:
                raise DecisionUnauthorized(str(exc)) from None
        self_authored = session["actor"]["id"] == proposer
        if kind.independence == "required" and self_authored:
            raise DecisionUnauthorized("An independent reviewer is required")
        classification_ids = self.inbox.classification_ids(item)
        if classification_ids:
            decisions = payload.get("item_decisions")
            if (
                not isinstance(decisions, dict)
                or set(decisions) != set(classification_ids)
                or any(v not in {"accept", "reject"} for v in decisions.values())
            ):
                raise ValueError(
                    "Every bound classification item needs an accept or reject decision"
                )
            if payload["outcome"] == "accept" and "reject" in decisions.values():
                raise ValueError("Overall acceptance requires all items accepted")
        if (
            kind.name in {"pilot-slice-approval", "reference-approval", "partner-share"}
            and session["actor"]["kind"] != "customer"
        ):
            raise DecisionUnauthorized("Customer identity required")
        # Parse/hash and execute trusted validators before taking the sole writer lock.
        # A changed journal head invalidates this preparation at commit time.
        validation = None
        if kind.name in self.validators:
            validation = self.validators[kind.name](
                item, payload, prepared_events, session
            )
        elif kind.name in {
            "rule-technical-review",
            "rule-approval",
            "rule-retirement",
            "qualification-acceptance",
            "evidence-release",
        }:
            raise DecisionConflict("Required evidence validator is not configured")
        if self.inbox.item(item["id"])["bound"] != item["bound"]:
            raise DecisionConflict("Evidence changed, review again")
        with self.transaction() as db:
            events = self.events(db)
            current_roles = self._roles(session["actor"]["id"], events)
            if not set(current_roles) & set(kind.roles) or {
                "auditor",
                "agent",
                "partner-viewer",
            } & set(current_roles):
                raise DecisionUnauthorized("Role assignment changed")
            session = {**session, "roles": current_roles}
            if "business-owner" in kind.roles:
                grant = next(
                    e
                    for e in reversed(events)
                    if e["kind"] == "roles_assigned"
                    and e["payload"]["actor_id"] == session["actor"]["id"]
                )
                workload = item.get("workload")
                if not workload or workload not in grant["payload"].get(
                    "workloads", []
                ):
                    raise DecisionUnauthorized(
                        "Business owner must be assigned to this workload"
                    )
            for event in events:
                if (
                    event["kind"] == "tower_decision"
                    and event["payload"]["request_id"] == request_id
                ):
                    if event["actor"] != session["actor"] or event["payload"][
                        "request_sha256"
                    ] != digest(payload):
                        raise DecisionConflict("Request ID already used")
                    return event
            if events != prepared_events:
                raise DecisionConflict(
                    "Journal changed during validation; review again"
                )
            latest = self._latest(events, item, slot)
            if payload.get("bound") != item["bound"] or payload.get(
                "previous_decision_sha256"
            ) != (latest or {}).get("content_sha256"):
                raise DecisionConflict("Evidence or decision changed, review again")
            if not any(
                e["kind"] == "tower_item_viewed"
                and e["session_id"] == session["id"]
                and e["payload"]["item_id"] == item["id"]
                and e["payload"]["bound"] == item["bound"]
                and (
                    e["payload"].get("previous_decisions_by_role", {}).get(slot)
                    if slot
                    else e["payload"].get("previous_decision_sha256")
                )
                == (latest or {}).get("content_sha256")
                for e in events
            ):
                raise DecisionConflict(
                    "View the current item in this session before deciding"
                )
            independence = (
                "not-applicable"
                if kind.independence == "not-applicable"
                else "operator-review" if self_authored else "independent"
            )
            # Operator-review-allowed is conservatively labelled operator review: a
            # different account alone is not evidence of organizational independence.
            if (
                kind.independence == "operator-review-allowed"
                or kind.name == "classification-acceptance"
            ):
                independence = "operator-review"
            value = {
                "schema": "tower-decision/1",
                "kind": kind.name,
                "kind_version": kind.version,
                "scope": self.scope,
                "item_id": item["id"],
                "bound": item["bound"],
                "outcome": payload["outcome"],
                "reason": payload["reason"],
                "named_owner": payload.get("named_owner"),
                "review_after": review_after,
                "actor": session["actor"],
                "roles_held": session["roles"],
                "session_id": session["id"],
                "authentication": session["authentication"],
                "proposed_by": proposer,
                "decider_is_proposer": self_authored,
                "independence": independence,
                "request_id": request_id,
                "request_sha256": digest(payload),
                "decision_slot": slot,
                "previous_decision_sha256": (latest or {}).get("content_sha256"),
                "channel": "control-tower",
                "verdict_changed": False,
                "validation": validation,
                "signature_type": "Service countersignature of authenticated operator intent",
            }
            if classification_ids:
                value["classification_item_ids"] = classification_ids
                value["item_decisions"] = dict(payload["item_decisions"])
            event = self.append(
                db, "tower_decision", value, session["actor"], session["id"]
            )
            if kind.name in self.finalizers:
                self.finalizers[kind.name](db, item, events + [event])
            if (
                kind.name == "difference-disposition"
                and payload["outcome"] == "intended-change"
            ):
                self.append(
                    db,
                    "rule_proposal_requested",
                    {
                        "scope": self.scope,
                        "item_id": item["id"],
                        "bound": item["bound"],
                        "decision_sha256": event["content_sha256"],
                        "status": "awaiting-typed-proposal",
                        "verdict_changed": False,
                    },
                    session["actor"],
                    session["id"],
                )
            return event

    def propose(self, token, proposal_type, payload):
        session = self._write_access(
            token, "propose", {"agent", "operator", "rule-proposer"}
        )
        if proposal_type not in {"rule-proposal", "classification-draft", "annotation"}:
            raise ValueError("Unsupported proposal type")
        request_id = str(
            uuid.UUID(text_field(payload.get("request_id"), "Request ID", 36))
        )
        item = self.inbox.item(payload.get("item_id"))
        if payload.get("bound") != item["bound"]:
            raise DecisionConflict("Evidence changed, review again")
        text_field(payload.get("text"), "Proposal", 10000)
        typed = None
        if proposal_type == "rule-proposal":
            from .rule_types import typed_rule

            typed = typed_rule(payload.get("rule", {}))
            if typed["proposed_by"] != session["actor"]["id"]:
                raise DecisionUnauthorized(
                    "Proposal author must be the authenticated actor"
                )
            if typed["workload"] != item.get("workload"):
                raise DecisionConflict("Rule workload does not match the request")
        # Drafts are journal records only, never engine requests or approvals.
        with self.transaction() as db:
            for e in self.events(db):
                if (
                    e["kind"] == "tower_proposal"
                    and e["payload"]["request_id"] == request_id
                ):
                    if (
                        e["payload"]["request_sha256"] != digest(payload)
                        or e["actor"] != session["actor"]
                    ):
                        raise DecisionConflict("Request ID already used")
                    return e
            return self.append(
                db,
                "tower_proposal",
                {
                    "scope": self.scope,
                    "proposal_type": proposal_type,
                    "item_id": item["id"],
                    "bound": item["bound"],
                    "text": payload["text"],
                    "request_id": request_id,
                    "request_sha256": digest(payload),
                    "label": (
                        "prepared by agent"
                        if "agent" in session["roles"]
                        else "operator proposal"
                    ),
                    "rule": typed,
                    "approval": False,
                },
                session["actor"],
                session["id"],
            )

    def export_session(self, token):
        session = self._read_access(token)
        with self.transaction() as db:
            events = self.events(db)
            return self.sign(
                {
                    "record_type": "tower-journal-export/1",
                    "scope": self.scope,
                    "events": events,
                    "exported_at": utcnow().isoformat(),
                    "journal_head_sha256": (
                        events[-1]["content_sha256"] if events else ZERO
                    ),
                    "signature_type": "Service countersignature of authenticated operator intent",
                }
            )

    def proof(self, token, decision_sha256):
        export = self.export_session(token)
        if not any(
            e["content_sha256"] == decision_sha256 and e["kind"] == "tower_decision"
            for e in export["events"]
        ):
            raise KeyError("Unknown scoped decision")
        return {
            "schema": "tower-decision-proof/1",
            "decision_sha256": decision_sha256,
            "journal": export,
        }
