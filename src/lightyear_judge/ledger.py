"""Judge-account cumulative inventory budget. Reservations are never refunded."""

from contextlib import contextmanager
from pathlib import Path
from lightyear_control_tower.decisions import ZERO, verify_envelope, digest
from lightyear_control_tower.status_export import atomic_new
from lightyear_mainframe.zos_evidence import Signer, initialize_key, read_json, now


def ledger_directory():
    import os
    import pwd

    # Deliberately ignore task paths, HOME and agent-provided environment overrides.
    return Path(pwd.getpwuid(os.geteuid()).pw_dir) / ".lightyear-verify-ledger"


class Ledger:
    def __init__(self, inventory_hash, limit, *, directory=None, tower_key=""):
        self.root = (directory or ledger_directory()) / inventory_hash
        self.root.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.root.mkdir(mode=0o700, exist_ok=True)
        import os

        if any(p.is_symlink() for p in (self.root, *self.root.parents)):
            raise ValueError("inventory-ledger-link-refused")
        if os.name != "nt" and (
            self.root.stat().st_uid != os.geteuid() or self.root.stat().st_mode & 0o077
        ):
            raise ValueError("inventory-ledger-not-private")
        self.inventory_hash = inventory_hash
        with self.locked():
            key_exists = (self.root / "authority.pem").exists()
            policy_exists = (self.root / "policy.json").exists()
            if key_exists != policy_exists:
                raise ValueError("inventory-ledger-incomplete")
            if not key_exists:
                initialize_key(self.root / "authority.pem")
            self.signer = Signer(self.root / "authority.pem")
            if not policy_exists:
                atomic_new(
                    self.root / "policy.json",
                    self.signer.sign(
                        dict(
                            schema="verify-inventory-budget/1",
                            inventory_sha256=inventory_hash,
                            attempt_slots=limit,
                            tower_public_key=tower_key,
                        )
                    ),
                )
            self.read()

    @contextmanager
    def locked(self):
        import fcntl

        with (self.root / "ledger.lock").open("a+b") as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            yield

    def read(self):
        policy = read_json(self.root / "policy.json")
        if (
            not verify_envelope(policy, self.signer.public)
            or policy["inventory_sha256"] != self.inventory_hash
        ):
            raise ValueError("inventory-policy-invalid")
        events, previous = [], ZERO
        for i, p in enumerate(sorted(self.root.glob("[0-9]*.json")), 1):
            e = read_json(p)
            if (
                p.name != f"{i:08}.json"
                or not verify_envelope(e, self.signer.public)
                or e["sequence"] != i
                or e["previous_sha256"] != previous
                or e["inventory_sha256"] != self.inventory_hash
            ):
                raise ValueError("inventory-ledger-invalid")
            events.append(e)
            previous = e["content_sha256"]
        limit = policy["attempt_slots"]
        used = 0
        previous = ZERO
        for e in events:
            if e["schema"] == "verify-inventory-budget-grant/1":
                self.verify_grant(policy, e, limit, used, previous)
                limit = e["new_limit"]
            elif e["schema"] == "verify-inventory-reservation/1":
                used += 1
                if used > limit:
                    raise ValueError("inventory-budget-exceeded")
            else:
                raise ValueError("inventory-event-invalid")
            previous = e["content_sha256"]
        return {**policy, "effective_limit": limit, "used": used}, events

    def budget(self):
        with self.locked():
            policy, events = self.read()
            return policy["effective_limit"], policy["used"]

    def reserve(self, task, attempt_id):
        with self.locked():
            policy, events = self.read()
            if policy["used"] >= policy["effective_limit"]:
                raise ValueError("inventory-budget-exhausted")
            event = self.signer.sign(
                dict(
                    schema="verify-inventory-reservation/1",
                    inventory_sha256=self.inventory_hash,
                    sequence=len(events) + 1,
                    previous_sha256=events[-1]["content_sha256"] if events else ZERO,
                    task_sha256=task,
                    attempt_id=attempt_id,
                    at_utc=now(),
                )
            )
            atomic_new(self.root / f"{len(events) + 1:08}.json", event)
            return event

    def grant_bindings(self, limit, used, head, new_limit):
        return {
            "inventory": digest({"inventory_sha256": self.inventory_hash}),
            "budget": digest({"limit": limit, "used": used, "head": head}),
            "new_limit": digest({"attempt_slots": new_limit}),
        }

    def verify_grant(self, policy, grant, limit, used, head):
        from lightyear_control_tower.verification import verify_decision
        import re

        if (
            not isinstance(grant["trusted_head"], str)
            or not re.fullmatch(r"[a-f0-9]{64}", grant["trusted_head"])
            or not policy["tower_public_key"]
            or type(grant["new_limit"]) is not int
            or not limit < grant["new_limit"] <= 100
        ):
            raise ValueError("inventory-grant-invalid")
        proof = grant["proof"]
        event = next(
            e
            for e in proof["journal"]["events"]
            if e["content_sha256"] == proof["decision_sha256"]
        )
        bound = event["payload"]["bound"]
        if any(
            bound.get(k) != v
            for k, v in self.grant_bindings(
                limit, used, head, grant["new_limit"]
            ).items()
        ):
            raise ValueError("inventory-grant-binding-invalid")
        verify_decision(
            proof,
            policy["tower_public_key"].encode(),
            "verify-budget-increase",
            bound,
            expected_head=grant["trusted_head"],
            scope=grant["scope"],
            outcomes=["approved"],
        )

    def grant(self, new_limit, proof, trusted_head, scope):
        with self.locked():
            policy, events = self.read()
            previous = events[-1]["content_sha256"] if events else ZERO
            body = dict(
                schema="verify-inventory-budget-grant/1",
                inventory_sha256=self.inventory_hash,
                sequence=len(events) + 1,
                previous_sha256=previous,
                at_utc=now(),
                new_limit=new_limit,
                proof=proof,
                trusted_head=trusted_head,
                scope=scope,
            )
            self.verify_grant(
                policy, body, policy["effective_limit"], policy["used"], previous
            )
            atomic_new(self.root / f"{len(events) + 1:08}.json", self.signer.sign(body))
