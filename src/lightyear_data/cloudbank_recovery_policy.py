"""Owner-approved recovery acceptance policy for the synthetic MS67 environment."""
from __future__ import annotations

from .contracts import seal

POLICY_ID = "ms67-nonproduction-pitr-rto-630-2026-09-10"
PREVIOUS_MAXIMUM_PITR_RTO_SECONDS = 600
MAXIMUM_PITR_RTO_SECONDS = 630
MAXIMUM_BACKUP_RESTORE_RTO_SECONDS = 600
MAXIMUM_RPO_SECONDS = 60


def recovery_acceptance_policy():
    return seal({
        "schema_version": "1.0",
        "policy_id": POLICY_ID,
        "scope": "ms67-synthetic-nonproduction-database-recovery",
        "authorized_by": "Howard Weale",
        "authorized_on": "2026-09-10",
        "reason": "Owner-approved noncustomer PITR recovery target; re-evaluate existing measurements.",
        "previous_maximum_pitr_rto_seconds": PREVIOUS_MAXIMUM_PITR_RTO_SECONDS,
        "maximum_pitr_rto_seconds": MAXIMUM_PITR_RTO_SECONDS,
        "maximum_backup_restore_rto_seconds": MAXIMUM_BACKUP_RESTORE_RTO_SECONDS,
        "maximum_rpo_seconds": MAXIMUM_RPO_SECONDS,
        "exact_state_required": True,
        "cleanup_required": True,
        "production_sla": False,
    })
