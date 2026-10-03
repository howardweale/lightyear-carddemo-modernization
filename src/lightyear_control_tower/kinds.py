"""Closed decision-kind registry. Plugins are trusted Python, never request code."""

from dataclasses import dataclass


@dataclass(frozen=True)
class DecisionKind:
    name: str
    outcomes: tuple[str, ...]
    roles: tuple[str, ...]
    hashes: tuple[str, ...]
    independence: str = "operator-review-allowed"
    required_fields: tuple[str, ...] = ("reason",)
    consumer: str = "headless-engine"
    version: int = 1
    proposer_roles: tuple[str, ...] = ("operator", "agent")
    source: str = "verified-request-inbox"
    verifier: str = "lightyear_control_tower.verify_decision"
    review_days: int = 5
    max_review_days: int = 366


class KindRegistry:
    def __init__(self, kinds=()):
        self._kinds = {}
        for kind in kinds:
            self.register(kind)

    def register(self, kind):
        if kind.name in self._kinds or not kind.outcomes or not kind.roles:
            raise ValueError("Duplicate or incomplete decision kind")
        if kind.independence not in {
            "required",
            "operator-review-allowed",
            "not-applicable",
        }:
            raise ValueError("Unknown independence policy")
        self._kinds[kind.name] = kind

    def get(self, name):
        if name not in self._kinds:
            raise ValueError("Unknown decision kind")
        return self._kinds[name]

    def names(self):
        return tuple(sorted(self._kinds))


def default_registry():
    K = DecisionKind
    return KindRegistry(
        [
            K(
                "verify-attempt-review",
                ("continue", "void"),
                ("campaign-authorizer",),
                ("receipt",),
                consumer="verify-next-attempt",
            ),
            K(
                "verify-budget-increase",
                ("approved", "rejected"),
                ("campaign-authorizer",),
                ("inventory", "budget", "new_limit"),
                consumer="verify-inventory-budget",
            ),
            K(
                "verify-normalization",
                ("approved", "rejected"),
                ("normalization-approver",),
                ("rule",),
                required_fields=("reason", "named_owner", "review_after"),
                consumer="judge-operator-rule-preparation",
            ),
            K(
                "intake-acceptance",
                ("accepted", "rejected"),
                ("qualification-approver",),
                ("intake",),
                consumer="carddemo-zos-intake",
            ),
            K(
                "normalization",
                ("approved", "rejected"),
                ("normalization-approver",),
                ("entry", "ledger"),
                required_fields=("reason", "named_owner", "review_after"),
                consumer="normalization-gate",
                source="normalization-ledger",
            ),
            K(
                "campaign-authorization",
                ("authorized", "rejected"),
                ("campaign-authorizer",),
                ("campaign", "plan", "declaration", "limits", "public_commit"),
                consumer="new-controller-launch",
            ),
            K(
                "b06-pause",
                ("continue", "stop", "void"),
                ("campaign-authorizer",),
                ("campaign", "plan", "executable", "pause"),
                consumer="b06-controller-next-slot",
            ),
            K(
                "freeze-approval",
                ("approved", "rejected"),
                ("campaign-authorizer",),
                ("snapshot", "qualification_report", "plan"),
                consumer="new-controller-launch",
            ),
            K(
                "measurement-validity",
                ("continue", "pause", "stop", "void"),
                ("campaign-authorizer",),
                ("campaign", "journal_head", "cause"),
                consumer="new-controller-trial-boundary",
            ),
            K(
                "classification-acceptance",
                ("accept", "reject"),
                ("classification-reviewer",),
                ("classification", "item_ids"),
                "required",
                consumer="publication",
            ),
            K(
                "resume",
                ("resume", "remain-paused"),
                ("campaign-authorizer",),
                ("campaign", "journal_head", "pause"),
                consumer="new-controller-trial-boundary",
            ),
            K(
                "difference-disposition",
                ("defect", "intended-change", "needs-information"),
                ("business-owner",),
                ("diagnostic", "observation_source", "observation_target", "workload"),
                "not-applicable",
                review_days=3,
            ),
            K(
                "rule-technical-review",
                ("approved", "rejected"),
                ("technical-reviewer",),
                ("rule", "still_caught", "ledger_validation"),
                "required",
                consumer="rule-register",
            ),
            K(
                "rule-approval",
                ("approved", "rejected"),
                ("business-owner",),
                ("rule", "technical_review", "workload"),
                "required",
                ("reason", "named_owner", "review_after"),
                "rule-register",
            ),
            K(
                "rule-retirement",
                ("retired", "renewed"),
                ("business-owner",),
                ("rule", "workload"),
                "required",
                ("reason", "named_owner", "review_after"),
                "rule-register",
            ),
            K(
                "qualification-acceptance",
                ("accepted", "rejected"),
                ("qualification-approver",),
                ("qualification", "replay"),
                consumer="catalogue",
            ),
            K(
                "requalification-request",
                ("requested",),
                ("campaign-authorizer",),
                ("qualification",),
                consumer="qualification-inbox",
            ),
            K(
                "pilot-slice-approval",
                ("approved", "rejected"),
                ("customer-sponsor",),
                ("slice",),
                "not-applicable",
            ),
            K(
                "evidence-release",
                ("approved", "rejected"),
                ("customer-sponsor", "campaign-authorizer"),
                ("archive",),
                "not-applicable",
                consumer="customer-export",
            ),
            K(
                "reference-approval",
                ("none", "anonymous", "named-logo", "named-quote", "case-study"),
                ("customer-sponsor",),
                ("asset",),
                "not-applicable",
            ),
            K(
                "partner-share",
                ("none", "status", "summary", "evidence"),
                ("customer-sponsor",),
                ("share",),
                "not-applicable",
            ),
        ]
    )


ROLES = frozenset(
    {
        "operator",
        "campaign-authorizer",
        "classification-reviewer",
        "rule-proposer",
        "technical-reviewer",
        "business-owner",
        "qualification-approver",
        "normalization-approver",
        "customer-sponsor",
        "partner-viewer",
        "auditor",
        "agent",
    }
)
APPROVING_ROLES = ROLES - {
    "operator",
    "rule-proposer",
    "partner-viewer",
    "auditor",
    "agent",
}
