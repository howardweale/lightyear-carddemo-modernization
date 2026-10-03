"""CardDemo workspace: decision kernel with a mandatory no-values boundary."""

from datetime import date
from uuid import UUID

from .console import ConsoleService
from .decisions import canonical, digest, DecisionUnauthorized, DecisionConflict, ZERO
from .requests import confined, read_json
from .verification import verify_decision, verify_journal
from . import carddemo_policy as p


class CarddemoConsole(ConsoleService):
    def __init__(self, root, authority, **kwargs):
        for person in read_json(authority)["operators"]:
            p.require(
                (person["name"], person["identity_kind"]) == p.PEOPLE.get(person["id"])
            )
        super().__init__(root, authority, registry=p.registry())
        self.inbox = p.Inbox(self.root, p.SCOPE, self.registry)
        self.validators = {k: self.validate for k in p.KINDS}
        # Existing journals with a different disclosure contract must not be exposed.
        with self.connect() as db:
            for event in self.events(db):
                p.require(event["payload"].get("disclosure_policy") == p.POLICY)

    def add_identity(self, operator_id, name, *, identity_kind="human"):
        p.require((name, identity_kind) == p.PEOPLE.get(operator_id))
        return super().add_identity(operator_id, name, identity_kind=identity_kind)

    def grant_roles(self, actor_id, roles, *, reason, workloads=()):
        p.require(actor_id in p.PEOPLE and set(workloads) <= {p.WORKLOAD})
        return super().grant_roles(actor_id, roles, reason=reason, workloads=workloads)

    def append(self, db, kind, payload, actor, session_id=None):
        # Before signing, commit to free text without retaining or publishing it.
        # The signing envelope itself is never redacted after signing.
        identities = p.PEOPLE | {
            "local-authority-administrator": (
                "Local authority administration",
                "service",
            ),
            "control-tower-proof-worker": ("Automated proof worker", "service"),
        }
        p.require(
            (actor.get("name"), actor.get("kind")) == identities.get(actor.get("id"))
        )
        payload = dict(payload, disclosure_policy=p.POLICY)
        for key in ("reason", "text"):
            if key in payload:
                payload[key] = "sha256:" + digest(payload[key])
        return super().append(db, kind, payload, actor, session_id)

    def events(self, db):
        from .decisions import verify_envelope

        events = super().events(db)
        previous = ZERO
        for n, event in enumerate(events, 1):
            p.require(
                verify_envelope(event, self.public_key)
                and event["sequence"] == n
                and event["previous_sha256"] == previous
                and event["payload"].get("disclosure_policy") == p.POLICY
            )
            previous = event["content_sha256"]
        return events

    def ledger(self):
        raise DecisionUnauthorized("Legacy ledger is disabled in this workspace")

    def validate(self, item, payload, events, session):
        kind = item["kind"]
        if kind != "evidence-release" and session["actor"]["id"] != p.HOWARD:
            raise DecisionUnauthorized("Howard must decide this request")
        if payload.get("named_owner") not in (None, p.HOWARD):
            raise ValueError("Named owner must be Howard's authenticated identity")
        if payload.get("review_after"):
            p.require(
                date.fromisoformat(payload["review_after"]).isoformat()
                == payload["review_after"]
            )
        result = dict(
            disclosure_policy=p.POLICY, operator_review=True, verdict_changed=False
        )
        if kind == "normalization":
            result["agent_proposal_sha256"] = p.agent_proposal(item, events)
        if kind == "evidence-release":
            slot = payload.get("decision_slot")
            expected = {
                "customer-sponsor": "release-sponsor",
                "campaign-authorizer": p.HOWARD,
            }
            p.require(session["actor"]["id"] == expected.get(slot))
            p.evidence(read_json(confined(self.root, item["evidence"]["archive"])))
            for event in events:
                if (
                    event["kind"] == "tower_decision"
                    and event["payload"].get("bound") == item["bound"]
                ):
                    if event["payload"].get("decision_slot") != slot:
                        p.require(event["actor"]["id"] != session["actor"]["id"])
        return result

    def propose(self, token, proposal_type, payload):
        session = self._write_access(token, "propose", {"agent"})
        p.require(
            session["actor"]["id"] == p.AGENT and session["actor"]["kind"] == "agent"
        )
        p.require(
            proposal_type in {"rule-proposal", "classification-draft", "annotation"}
        )
        request_id = str(UUID(payload["request_id"]))
        item = self.inbox.item(payload["item_id"])
        if item["bound"] != payload["bound"]:
            raise DecisionConflict("Evidence changed")
        typed = None
        if proposal_type == "rule-proposal":
            p.require(item["kind"] == "normalization")
            typed = p.rule(payload["rule"])
            p.require(p.sha(canonical(typed) + b"\n") == item["bound"]["rule"])
        with self.transaction() as db:
            for event in self.events(db):
                if (
                    event["kind"] == "tower_proposal"
                    and event["payload"]["request_id"] == request_id
                ):
                    p.require(event["payload"]["request_sha256"] == digest(payload))
                    return event
            return self.append(
                db,
                "tower_proposal",
                dict(
                    scope=p.SCOPE,
                    proposal_type=proposal_type,
                    item_id=item["id"],
                    bound=item["bound"],
                    text=payload.get("text", ""),
                    request_id=request_id,
                    request_sha256=digest(payload),
                    label="prepared by agent",
                    rule=typed,
                    approval=False,
                ),
                session["actor"],
                session["id"],
            )

    def queue(self, token):
        result = super().queue(token)
        for item in result["items"]:
            if item.get("status") == "invalid":
                continue
            if item["kind"] != "evidence-release":
                item["decidable"] &= result["session"]["actor"]["id"] == p.HOWARD
            if item["kind"] == "normalization":
                with self.connect() as db:
                    try:
                        p.agent_proposal(item, self.events(db))
                    except ValueError:
                        item.update(
                            decidable=False,
                            decision_refusal="authenticated-agent-proposal-required",
                        )
        result["disclosure_policy"] = p.POLICY
        return result

    def item(self, token, item_id):
        result = super().item(token, item_id)
        result["evidence_view"] = self.safe_evidence(result)
        return result

    def review(self, token, item_id):
        result = super().review(token, item_id)
        result["evidence_view"] = self.safe_evidence(result)
        return result

    def safe_evidence(self, item):
        return {
            k: p.evidence(read_json(confined(self.root, rel)))
            for k, rel in item["evidence"].items()
        }

    def catalogue(self, token):
        self._read_access(token)
        return dict(scope=p.SCOPE, entries=[], disclosure_policy=p.POLICY)

    def campaign_status(self, token, campaign_id):
        self._read_access(token)
        return dict(
            scope=p.SCOPE,
            available=False,
            reason="No campaign adapter in intake workspace",
        )

    def arrivals(self, token):
        self._read_access(token)
        return dict(
            scope=p.SCOPE,
            disclosure_policy=p.POLICY,
            read_only=True,
            arrivals=[
                dict(request_id=i["id"], **self.safe_evidence(i)["intake"])
                for i in self.inbox.queue()
                if i.get("kind") == "intake-acceptance"
            ],
        )

    def register(self, token):
        journal = self.export_session(token)
        rows = []
        for event in journal["events"]:
            v = event["payload"]
            if (
                event["kind"] != "tower_decision"
                or v["kind"] != "normalization"
                or v["outcome"] != "approved"
            ):
                continue
            proof = dict(
                schema="tower-decision-proof/1",
                decision_sha256=event["content_sha256"],
                journal=journal,
            )
            try:
                verify_decision(
                    proof,
                    self.public_key,
                    "normalization",
                    v["bound"],
                    expected_head=journal["journal_head_sha256"],
                    scope=p.SCOPE,
                    outcomes=["approved"],
                )
            except ValueError:
                continue
            proposal = next(
                e
                for e in journal["events"]
                if e["content_sha256"] == v["validation"]["agent_proposal_sha256"]
            )
            rows.append(dict(rule=p.rule(proposal["payload"]["rule"]), proof=proof))
        return self.sign(
            dict(
                schema="zos-rule-register/1",
                scope=p.SCOPE,
                disclosure_policy=p.POLICY,
                journal_head_sha256=journal["journal_head_sha256"],
                rules=rows,
            )
        )

    def release(self, token, item_id):
        self._read_access(token)
        item = self.inbox.item(item_id)
        p.require(item["kind"] == "evidence-release")
        journal = self.export_session(token)
        proofs = []
        for role in self.registry.get("evidence-release").roles:
            event = self._latest(journal["events"], item, role)
            if not event:
                raise DecisionUnauthorized("Both release decisions are required")
            proof = dict(
                schema="tower-decision-proof/1",
                decision_sha256=event["content_sha256"],
                journal=journal,
            )
            verify_decision(
                proof,
                self.public_key,
                "evidence-release",
                item["bound"],
                expected_head=journal["journal_head_sha256"],
                scope=p.SCOPE,
                outcomes=["approved"],
            )
            proofs.append(proof)
        bundle = self.safe_evidence(item)["archive"]
        result = self.sign(
            dict(
                schema="zos-released-export/1",
                scope=p.SCOPE,
                disclosure_policy=p.POLICY,
                bundle=bundle,
                proofs=proofs,
                journal_head_sha256=journal["journal_head_sha256"],
            )
        )
        verify_release(result, self.public_key)
        return result


class CarddemoAPI:
    """Closed transport map: generic estate, campaign and file adapters are not used."""

    def __init__(self, service):
        self.service = service

    def read(self, route, token, args):
        s = self.service
        s._read_access(token)
        if route == "workspace":
            return dict(
                scope=p.SCOPE,
                configured=True,
                title="CardDemo z/OS arrivals",
                disclosure_policy=p.POLICY,
                **{
                    k: v
                    for k, v in s.arrivals(token).items()
                    if k != "scope" and k != "disclosure_policy"
                },
            )
        if route == "arrivals":
            return s.arrivals(token)
        if route == "queue":
            return s.queue(token)
        if route == "item":
            return s.item(token, args["id"])
        if route == "history":
            return s.export_session(token)
        if route == "proof":
            return s.proof(token, args["sha256"])
        if route == "rules":
            return s.register(token)
        if route == "catalogue":
            return s.catalogue(token)
        if route == "campaigns":
            return {"campaigns": []}
        if route == "campaign":
            return s.campaign_status(token, args.get("id"))
        if route == "export":
            return s.release(token, args["id"])
        if route == "validation":
            item = s.inbox.item(args["id"])
            return dict(
                disclosure_policy=p.POLICY,
                bound=item["bound"],
                evidence=s.safe_evidence(item),
            )
        if route == "events":
            return dict(
                scope=p.SCOPE,
                queue=s.queue(token),
                arrivals=s.arrivals(token),
                campaigns=[],
            )
        raise KeyError("Unknown read route")


def verify_release(value, key):
    from .decisions import verify_envelope

    p.require(
        verify_envelope(value, key) and value.get("schema") == "zos-released-export/1"
    )
    p.require(
        set(value)
        == {
            "schema",
            "scope",
            "disclosure_policy",
            "bundle",
            "proofs",
            "journal_head_sha256",
            "content_sha256",
            "signature",
        }
    )
    p.require(value["scope"] == p.SCOPE and value["disclosure_policy"] == p.POLICY)
    p.evidence(value["bundle"])
    p.require(len(value["proofs"]) == 2)
    roles, actors = set(), set()
    for proof in value["proofs"]:
        events = verify_journal(
            proof["journal"],
            key,
            scope=p.SCOPE,
            expected_head=value["journal_head_sha256"],
        )
        event = next(
            e for e in events if e["content_sha256"] == proof["decision_sha256"]
        )
        bound = event["payload"]["bound"]
        p.require(bound["archive"] == p.sha(canonical(value["bundle"]) + b"\n"))
        decision = verify_decision(
            proof,
            key,
            "evidence-release",
            bound,
            scope=p.SCOPE,
            expected_head=value["journal_head_sha256"],
            outcomes=["approved"],
        )
        roles.add(decision["decision_slot"])
        actors.add(decision["actor"]["id"])
    p.require(roles == {"customer-sponsor", "campaign-authorizer"} and len(actors) == 2)
    return dict(status="verified", scope=p.SCOPE, disclosure_policy=p.POLICY)
