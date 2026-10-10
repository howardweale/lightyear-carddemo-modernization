"""Small target adapter contract: each edit belongs to one reviewed rule anchor."""
from dataclasses import dataclass
from typing import Protocol
from hashlib import sha256
from .language import require

@dataclass(frozen=True)
class Edit:
    name: str
    old: str
    new: str
    target: str = "service"

class Adapter(Protocol):
    def edits(self, rule: dict) -> list[Edit]: ...

class CardDemoAdapter:
    def edits(self, rule):
        if not rule.get("executable") or not rule.get("derived_from"):
            return []
        suffix = rule["id"].split(":")[-1]
        monthly = ".divide(BigDecimal.valueOf(1200), 2, RoundingMode.DOWN)"
        if suffix == "monthly-interest" and rule["executable"]["form"] == "expression":
            return [Edit("rounding-mode", monthly, monthly.replace("DOWN", "HALF_UP")),
                Edit("scale-minus-one", monthly, monthly.replace(", 2,", ", 1,")),
                Edit("scale-plus-one", monthly, monthly.replace(", 2,", ", 3,")),
                Edit("operand-swap", monthly, ".divide(balance.balance().multiply(disclosure.annualRate()), 2, RoundingMode.DOWN)"),
                Edit("constant-zero", monthly, monthly+".multiply(BigDecimal.ZERO)")]
        if suffix == "disclosure-rate":
            return [Edit("drop-direct-rate", "Disclosure disclosure = disclosureByKey.get(key);", "Disclosure disclosure = null;")]
        if suffix == "default-rate":
            return [Edit("drop-default-branch", "if (disclosure == null) {", "if (false) {")]
        if suffix in {"zero-rate", "nonzero-rate-emission"}:
            return [Edit("comparison-boundary", "disclosure.annualRate().signum() == 0", "disclosure.annualRate().signum() < 0"),
                    Edit("drop-zero-branch", "disclosure.annualRate().signum() == 0", "false")]
        if suffix == "account-boundary":
            return [Edit("drop-account-boundary", "!Objects.equals(balance.accountId(), currentAccountId)", "currentAccountId == null")]
        if suffix == "source-final-account":
            return [Edit("drop-final-branch", '\"intended\".equals(finalAccountPolicy) && currentAccount != null', "currentAccount != null")]
        if suffix == "interest-transaction":
            return [Edit("record-offset", "int suffix = generated.size() + 1;", "int suffix = generated.size() + 2;")]
        return []


def anchored_variants(source, rule, adapter):
    for edit in adapter.edits(rule):
        require(source.count(edit.old) == 1, "rule-mutation-anchor-changed")
        start = source.index(edit.old)
        changed = source[:start] + edit.new + source[start+len(edit.old):]
        # Explicit modern span linked to this rule's original source anchors.
        yield dict(name=edit.name, text=changed, target=edit.target, rule_id=rule["id"],
                   anchor=dict(legacy=rule["derived_from"], start_line=source[:start].count("\n")+1,
                               end_line=source[:start+len(edit.old)].count("\n")+1,
                               original_sha256=sha256(edit.old.encode()).hexdigest()))
