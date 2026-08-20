"""Bounded, source-faithful candidate for the CardDemo CBPAUP0C IMS BMP cell."""

from __future__ import annotations

import copy
from decimal import Decimal
from typing import Any


PROGRAM_ID = "CBPAUP0C"
PSB_NAME = "PSBPAUTB"
DATABASE_NAME = "DBPAUTP0"
PCB_NAME = "PAUTBPCB"
PCB_NUMBER = 2
PROCOPT = "AP"
ROOT_SEGMENT = "PAUTSUM0"
DETAIL_SEGMENT = "PAUTDTL1"
DEFAULT_EXPIRY_DAYS = 5
SUMMARY_DELETE_POLICY = "approved-count-duplicated"
CHECKPOINT_POLICY = "strictly-greater-than-frequency-plus-final"


def _money(value: Any) -> Decimal:
    return Decimal(str(value))


def _money_text(value: Any) -> str:
    return format(_money(value), ".2f")


def _expiry_days(value: Any) -> int:
    text = str(value).strip()
    return int(text) if len(text) == 2 and text.isdigit() else DEFAULT_EXPIRY_DAYS


def _is_expired(current_yyddd: int, inverted_auth_date: int, expiry_days: int) -> bool:
    auth_date = 99999 - int(inverted_auth_date)
    return current_yyddd - auth_date >= expiry_days


def purge_expired_authorizations(
    summaries: list[dict[str, Any]],
    *,
    current_yyddd: int,
    expiry_days: Any = "05",
    checkpoint_frequency: int = 5,
) -> dict[str, Any]:
    """Apply the normal-path logical behavior of CBPAUP0C to an in-memory IMS hierarchy.

    This intentionally preserves the source's duplicated approved-count root deletion test.
    It models GN/GNP/DLET/CHKP ordering, but not IMS locking, status codes, recovery, or bytes.
    """
    records = copy.deepcopy(summaries)
    days = _expiry_days(expiry_days)
    kept: list[dict[str, Any]] = []
    deleted_details: list[dict[str, Any]] = []
    deleted_summary_ids: list[str] = []
    access_trace: list[dict[str, Any]] = []
    checkpoints: list[dict[str, Any]] = []
    summary_since_checkpoint = 0
    totals = {
        "summaries_read": 0,
        "summaries_deleted": 0,
        "details_read": 0,
        "details_deleted": 0,
    }

    for summary in records:
        account_id = str(summary["account_id"])
        totals["summaries_read"] += 1
        summary_since_checkpoint += 1
        access_trace.append({"operation": "GN", "segment": ROOT_SEGMENT, "account_id": account_id})

        remaining_details: list[dict[str, Any]] = []
        for detail in summary.get("details", []):
            totals["details_read"] += 1
            detail_id = str(detail["authorization_id"])
            access_trace.append(
                {"operation": "GNP", "segment": DETAIL_SEGMENT, "account_id": account_id, "authorization_id": detail_id}
            )
            if not _is_expired(current_yyddd, int(detail["inverted_auth_date"]), days):
                remaining_details.append(detail)
                continue

            if str(detail["response_code"]) == "00":
                summary["approved_count"] = int(summary["approved_count"]) - 1
                summary["approved_amount"] = _money(summary["approved_amount"]) - _money(detail["approved_amount"])
            else:
                summary["declined_count"] = int(summary["declined_count"]) - 1
                summary["declined_amount"] = _money(summary["declined_amount"]) - _money(detail["transaction_amount"])
            totals["details_deleted"] += 1
            deleted_details.append({"account_id": account_id, "authorization_id": detail_id})
            access_trace.append(
                {"operation": "DLET", "segment": DETAIL_SEGMENT, "account_id": account_id, "authorization_id": detail_id}
            )

        summary["details"] = remaining_details
        summary["approved_amount"] = _money_text(summary["approved_amount"])
        summary["declined_amount"] = _money_text(summary["declined_amount"])

        # Source-faithful: CBPAUP0C tests PA-APPROVED-AUTH-CNT twice and does not
        # consult PA-DECLINED-AUTH-CNT before deleting the root segment.
        delete_summary = int(summary["approved_count"]) <= 0 and int(summary["approved_count"]) <= 0
        if delete_summary:
            totals["summaries_deleted"] += 1
            deleted_summary_ids.append(account_id)
            access_trace.append({"operation": "DLET", "segment": ROOT_SEGMENT, "account_id": account_id})
        else:
            kept.append(summary)

        if summary_since_checkpoint > int(checkpoint_frequency):
            checkpoints.append({"reason": "frequency", "after_account_id": account_id})
            access_trace.append({"operation": "CHKP", "segment": None, "account_id": account_id})
            summary_since_checkpoint = 0

    final_account = str(records[-1]["account_id"]) if records else None
    checkpoints.append({"reason": "final", "after_account_id": final_account})
    access_trace.append({"operation": "CHKP", "segment": None, "account_id": final_account})
    return {
        "program": PROGRAM_ID,
        "psb": PSB_NAME,
        "database": DATABASE_NAME,
        "pcb": PCB_NAME,
        "current_yyddd": int(current_yyddd),
        "expiry_days": days,
        "summaries": kept,
        "deleted_details": deleted_details,
        "deleted_summary_ids": deleted_summary_ids,
        "access_trace": access_trace,
        "checkpoints": checkpoints,
        "totals": totals,
        "source_quirks": [SUMMARY_DELETE_POLICY],
    }
