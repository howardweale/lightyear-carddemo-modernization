"""Target-neutral native boundary; execution requires an explicit VM connector."""
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any
import math

from lightyear_data.semantic_core import CANONICAL_TYPES

OBSERVABLES = ("result_sets","output_parameters","return_code","error","side_effects",
               "transaction","row_count_messages","informational_messages","temp_objects")


class NativeExecutionUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class EngineProfile:
    engine: str
    version: str
    image_digest: str | None
    compatibility_level: int | None
    collation: str
    session_settings: dict[str, Any]
    extensions: tuple[str, ...] = ()


@dataclass(frozen=True)
class Coverage:
    statements_total: int
    statements_hit: int
    branches_total: int
    branches_hit: int
    reachable_error_paths: tuple[str, ...]
    hit_error_paths: tuple[str, ...]
    uncovered_lines: tuple[int, ...]
    collector: str

    def validate(self):
        for total,hit in ((self.statements_total,self.statements_hit),(self.branches_total,self.branches_hit)):
            if type(total) is not int or type(hit) is not int or not 0<=hit<=total:
                raise ValueError("invalid-coverage-count")
        if not self.collector or not set(self.hit_error_paths)<=set(self.reachable_error_paths):
            raise ValueError("invalid-coverage-provenance")
        if self.statements_total==0: raise ValueError("empty-statement-coverage")


@dataclass(frozen=True)
class Observation:
    result_sets: list[dict]
    output_parameters: dict
    return_code: int
    error: dict | None
    raw_error: dict | None
    side_effects: dict
    transaction: dict
    row_count_messages: list[int]
    informational_messages: list[dict]
    temp_objects: list[str]
    elapsed_seconds: float
    engine_version: str
    session_settings: dict
    coverage: Coverage | None

    def validate(self):
        if type(self.return_code) is not int or not math.isfinite(self.elapsed_seconds) or self.elapsed_seconds<0 or not self.engine_version:
            raise ValueError("incomplete-observation")
        if self.transaction.get("outcome") not in {"committed","rolled-back","partial"}:
            raise ValueError("transaction-outcome-required")
        if (self.side_effects.get("all_user_tables_captured") is not True
            or not isinstance(self.side_effects.get("table_inventory"),list)
            or not isinstance(self.side_effects.get("tables"),dict)
            or not isinstance(self.side_effects.get("identity_sequence_state"),dict)):
            raise ValueError("all-table-capture-required")
        if (len(self.side_effects["table_inventory"])!=len(set(self.side_effects["table_inventory"]))
            or set(self.side_effects["tables"]) != set(self.side_effects["table_inventory"])):
            raise ValueError("side-effect-scope-incomplete")
        for result in self.result_sets:
            if set(result)!={"columns","rows","ordered"} or type(result["ordered"]) is not bool:
                raise ValueError("result-set-shape")
            for c in result["columns"]:
                if set(c)!={"name","canonical_type"} or c["canonical_type"] not in CANONICAL_TYPES:
                    raise ValueError("canonical-result-type")
            if any(len(r)!=len(result["columns"]) for r in result["rows"]):
                raise ValueError("result-row-width")
        if self.coverage: self.coverage.validate()


class EngineAdapter(ABC):
    """Implementations must capture TDS/refcursor semantics without an outer rollback."""
    @abstractmethod
    def provision(self, schema_bundle, data_bundle) -> dict: ...
    @abstractmethod
    def reset(self, environment, state_id) -> dict: ...
    @abstractmethod
    def call(self, environment, procedure, arguments, session_settings) -> Observation | dict:
        """Return an observation or raw native capture bundle awaiting admission."""
        ...
    @abstractmethod
    def capture_state(self, environment, table_scope) -> dict: ...
    @abstractmethod
    def coverage(self, environment, procedure) -> Coverage | dict | None: ...


class _NativeAdapter(EngineAdapter):
    def __init__(self, profile: EngineProfile, *, connector=None, owned_prefix=None, coverage_bridge=None):
        self.profile=profile
        self.backend=None
        if connector is not None:
            from .native import NativeEngine
            self.backend=NativeEngine(profile.engine,connector,owned_prefix,coverage_bridge)

    def _unavailable(self):
        raise NativeExecutionUnavailable("native-backend-not-installed; approved separate Linux VM required")

    def provision(self, schema_bundle, data_bundle):
        if self.backend is None: return self._unavailable()
        return self.backend.provision(schema_bundle['suffix'],schema_bundle['sql'],data_bundle['procedure_sql'])
    def reset(self, environment, state_id):
        if self.backend is None: return self._unavailable()
        return self.backend.reset(environment,state_id)
    def call(self, environment, procedure, arguments, session_settings):
        if self.backend is None: return self._unavailable()
        if arguments!=procedure['parameters'] or session_settings!=procedure['cases'][0]:
            raise ValueError('native-call-plan-mismatch')
        return self.backend.call(environment,procedure)
    def capture_state(self, environment, table_scope):
        if self.backend is None: return self._unavailable()
        if table_scope!='all-user-tables': raise ValueError('partial-table-scope-forbidden')
        return self.backend.capture_state(environment)
    def coverage(self, environment, procedure):
        if self.backend is None: return self._unavailable()
        return self.backend.coverage(environment,procedure)


class SqlServerAdapter(_NativeAdapter):
    reset_methods=("database-snapshot-revert","golden-backup-restore")
    coverage_collector="extended-events-start-complete-plus-scriptdom-spans"
    forbidden_reset="outer-transaction-rollback"


class PostgresAdapter(_NativeAdapter):
    """PostgreSQL/AlloyDB share protocol; exact version/extensions remain plan-bound."""
    reset_methods=("fresh-database-from-template",)
    coverage_collector="plpgsql_check-profiler-with-conservative-handler-gate"
    forbidden_reset="outer-transaction-rollback"


def coverage_gate(source: Coverage | None, target: Coverage | None,
                  statement_threshold=.90, branch_threshold=.80) -> dict:
    if not 0<=statement_threshold<=1 or not 0<=branch_threshold<=1:
        raise ValueError("coverage-threshold")
    lanes={}
    for name,c in (("source",source),("target",target)):
        if c is None:
            lanes[name]={"status":"insufficient-evidence","reason":"coverage-unavailable"}
            continue
        c.validate()
        statements=c.statements_hit/c.statements_total
        branches=c.branches_hit/c.branches_total if c.branches_total else 1.0
        missing=sorted(set(c.reachable_error_paths)-set(c.hit_error_paths))
        lanes[name]={"status":"threshold-met" if statements>=statement_threshold and branches>=branch_threshold and not missing else "insufficient-evidence",
                     "statements":statements,"branches":branches,"missing_error_paths":missing,
                     "uncovered_lines":list(c.uncovered_lines),"collector":c.collector}
    return {"eligible":all(x["status"]=="threshold-met" for x in lanes.values()),
            "lanes":lanes,"native_provenance_checked":False}
