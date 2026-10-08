"""Optional factory routing. No campaign entry point imports this module."""

from datetime import date, datetime, timezone
from lightyear_control_tower.decisions import digest
from .knowledge_trust import approve
from .providers import ProviderError
from .budgeted_providers import AccountedModelProvider
from .contracts import ContractError, canonical_hash

TASKS = {
    "plan",
    "implement",
    "repair-from-closed-diagnostic",
    "review",
    "normalization-proposal",
}


def admitted_policy(policy, matrix, proof, trust, *, now=None, versions=None):
    now = now or datetime.now(timezone.utc)
    if proof is None:
        return None
    try:
        from .routing_policy import compile_policy
        if policy != compile_policy(matrix, margin=policy['rule']['margin']):
            return None
        d = approve(
            proof,
            trust,
            "model-routing-policy",
            dict(policy=digest(policy), matrix_receipt=digest(matrix)),
            ["approved"],
            now=now,
        )
        expiry = date.fromisoformat(d["review_after"])
        if not 0 < (expiry - now.date()).days <= 90:
            return None
        event = next(
            e
            for e in proof["journal"]["events"]
            if e["content_sha256"] == proof["decision_sha256"]
        )
        issued = datetime.fromisoformat(event["occurred_at"])
        if (expiry - issued.date()).days > 90:
            return None
        if (
            matrix.get("schema") != "factory-evaluation-matrix/1"
            or matrix["false_acceptances"] != 0
            or matrix.get("content_sha256")
            != digest({k: v for k, v in matrix.items() if k != "content_sha256"})
        ):
            return None
        if set(policy["routes"]) - TASKS:
            return None
        for task, route in policy["routes"].items():
            if matrix["content_sha256"] not in route["matrix_receipts"]:
                return None
            for model in (route["primary"], route.get("fallback")):
                if not model:continue
                cells=[c for c in matrix['cells'] if c['model']==model and c['task_type']==task]
                if not cells:return None
                for c in cells:
                    if (c.get('run_count',0)<35 or len(set(c.get('runs',[])))!=c['run_count'] or
                            len(set(c.get('pair_ids',[])))!=c['run_count'] or
                            c.get('model_version')!=policy['model_versions'].get(model) or
                            versions is not None and versions.get(model)!=c['model_version']):return None
        return dict(
            policy=policy, sha256=digest(policy), review_after=d["review_after"]
        )
    except (ValueError, KeyError, TypeError, StopIteration):
        return None


class TaskRouter:
    provider_id = "factory-model-router"

    def __init__(
        self,
        providers,
        default,
        *,
        policy=None,
        matrix=None,
        proof=None,
        trust=None,
        now=None,
    ):
        if default not in providers:
            raise ValueError("default model not configured")
        self.providers, self.default, self.model = providers, default, default
        self.policy, self.matrix, self.proof, self.trust = policy, matrix, proof, trust
        self.clock = now or (lambda: datetime.now(timezone.utc))

    def bind_order(self, order):
        if order.metadata.get("campaign_id") or order.metadata.get(
            "calibration_campaign"
        ):
            raise ContractError("campaigns cannot use factory routing")
        return RoutedBudget(self, order)


class RoutedBudget:
    def __init__(self, router, order):
        self.router = router
        self.budget = AccountedModelProvider(router.providers[router.default], order)
        self.routing = []

    @property
    def calls(self):
        return self.budget.calls

    def complete(self, role, instruction, payload, schema):
        task = {
            "planner": "plan",
            "builder": (
                "repair-from-closed-diagnostic"
                if payload.get("public_failure")
                else "implement"
            ),
            "failure_analyst": "review",
        }.get(role, role)
        if task not in TASKS:
            raise ContractError("unknown routed task")
        r = self.router
        admitted = admitted_policy(r.policy, r.matrix, r.proof, r.trust, now=r.clock(),
            versions={m:p.model for m,p in r.providers.items()})
        route = (
            admitted["policy"]["routes"].get(task, {"primary": r.default})
            if admitted
            else {"primary": r.default}
        )
        models = [route["primary"]]
        if route.get("fallback") and route["fallback"] != models[0]:
            models.append(route["fallback"])
        for i, model in enumerate(models):
            if model not in r.providers:
                raise ContractError("routed model unavailable")
            provider = r.providers[model]
            # All attempts share one budget. The failed primary cannot disappear.
            if len(models) > 1 and not getattr(
                provider, "manage_failure_budget", False
            ):
                raise ContractError("fallback provider requires failure accounting")
            self.budget.provider = provider
            choice = dict(
                task_type=task,
                model=model,
                policy_sha256=admitted["sha256"] if admitted else None,
                fallback=i > 0,
            )
            self.routing.append(choice)
            try:
                result = self.budget.complete(role, instruction, payload, schema)
                evidence = {**result.evidence, "routing": choice}
                evidence["content_sha256"] = canonical_hash(
                    evidence, {"content_sha256"}
                )
                self.budget.calls[-1] = evidence
                return type(result)(result.content, evidence)
            except ProviderError:
                if i == len(models) - 1:
                    raise
        raise AssertionError("unreachable")

    def summary(self):
        result = self.budget.summary()
        result.update(provider="factory-model-router", model=None, routing=self.routing)
        result["content_sha256"] = canonical_hash(result, {"content_sha256"})
        return result
