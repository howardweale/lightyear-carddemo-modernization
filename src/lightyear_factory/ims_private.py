from __future__ import annotations

from types import ModuleType
import importlib.util
import json
from pathlib import Path
import sys


def _fixture() -> list[dict[str, object]]:
    return [
        {
            "account_id": "00000000001",
            "approved_count": 1,
            "declined_count": 1,
            "approved_amount": "40.00",
            "declined_amount": "25.00",
            "details": [
                {
                    "authorization_id": "APPROVED-OLD",
                    "inverted_auth_date": 79823,
                    "response_code": "00",
                    "approved_amount": "40.00",
                    "transaction_amount": "40.00",
                },
                {
                    "authorization_id": "DECLINED-NEW",
                    "inverted_auth_date": 79820,
                    "response_code": "05",
                    "approved_amount": "0.00",
                    "transaction_amount": "25.00",
                },
            ],
        },
        {
            "account_id": "00000000002",
            "approved_count": 1,
            "declined_count": 1,
            "approved_amount": "10.00",
            "declined_amount": "12.00",
            "details": [
                {
                    "authorization_id": "DECLINED-OLD",
                    "inverted_auth_date": 79824,
                    "response_code": "05",
                    "approved_amount": "0.00",
                    "transaction_amount": "12.00",
                }
            ],
        },
    ]


def policy_checks(candidate: ModuleType) -> dict[str, bool]:
    result = candidate.purge_expired_authorizations(
        _fixture(), current_yyddd=20181, expiry_days="05", checkpoint_frequency=1
    )
    second = result["summaries"][0]
    operations = [(item["operation"], item["segment"]) for item in result["access_trace"]]
    defaulted = candidate.purge_expired_authorizations([], current_yyddd=20181, expiry_days="XX")
    return {
        "ims_identity": (
            candidate.PROGRAM_ID,
            candidate.PSB_NAME,
            candidate.DATABASE_NAME,
            candidate.PCB_NAME,
            candidate.PCB_NUMBER,
            candidate.PROCOPT,
            candidate.ROOT_SEGMENT,
            candidate.DETAIL_SEGMENT,
        ) == ("CBPAUP0C", "PSBPAUTB", "DBPAUTP0", "PAUTBPCB", 2, "AP", "PAUTSUM0", "PAUTDTL1"),
        "inverted_date_boundary": result["totals"]["details_deleted"] == 2,
        "approved_detail_adjustment": result["deleted_summary_ids"] == ["00000000001"],
        "declined_detail_adjustment": str(second["declined_amount"]) == "0.00" and second["declined_count"] == 0,
        "source_duplicate_root_delete_test": (
            candidate.SUMMARY_DELETE_POLICY == "approved-count-duplicated"
            and result["deleted_summary_ids"] == ["00000000001"]
        ),
        "gn_gnp_dlet_order": operations[:4] == [
            ("GN", "PAUTSUM0"),
            ("GNP", "PAUTDTL1"),
            ("DLET", "PAUTDTL1"),
            ("GNP", "PAUTDTL1"),
        ],
        "strict_checkpoint_and_final": result["checkpoints"] == [
            {"reason": "frequency", "after_account_id": "00000000002"},
            {"reason": "final", "after_account_id": "00000000002"},
        ],
        "invalid_expiry_defaults_to_five": defaulted["expiry_days"] == 5,
    }


def all_checks_pass(candidate: ModuleType) -> bool:
    return all(policy_checks(candidate).values())


def main() -> int:
    path = Path(__file__).resolve().parents[2] / "factory/benchmarks/ims_expiry_candidate.py"
    spec = importlib.util.spec_from_file_location("factorydark_ims_candidate", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("IMS candidate cannot be loaded")
    candidate = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = candidate
    spec.loader.exec_module(candidate)
    checks = policy_checks(candidate)
    print(json.dumps({"checks": checks, "status": "passed" if all(checks.values()) else "failed"}, indent=2, sort_keys=True))
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
