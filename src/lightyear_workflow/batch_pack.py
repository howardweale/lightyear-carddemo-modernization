"""Declarative batch invocation. A job pack replaces hand-written driver code.

`cloudbank_journeys.py` couples the driver to one application in three places:
a `SCENARIOS` tuple, an `operations()` list of bound methods, and a hand-written
method per scenario. That is correct for a reference estate and impossible for a
customer's, because we would be writing their business journeys for them.

A batch job has the cleanest interface available:

    input datasets  ->  JCL  ->  output datasets

Deterministic, replayable, comparable byte for byte once representation is
normalized. So batch invocation is a manifest, not code — and the manifest is
written by whoever runs the schedule, which is never us.

The asymmetry that makes this acceptable to a change board:

    source lane   OBSERVED. We retrieve what production already ran.
                  Nothing is submitted. Nothing is mutated. Ever.
    target lane   REPLAYED. The same inputs, against the converted application.

That asymmetry is enforced here, not documented: `SourceLane` has no submit
method, and `validate_pack` refuses a pack that asks the source to run anything.
"""

from __future__ import annotations

from lightyear_common.evidence import evidence_floor

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence
import json
import re

SCHEMA_VERSION = "1.0"
PACK_TYPE = "lightyear-batch-job-pack"

# A dataset name we will accept. Conservative on purpose: anything we cannot
# parse is refused rather than passed to a mainframe interface.
DATASET = re.compile(r"^[A-Z#@$][A-Z0-9#@$]{0,7}(\.[A-Z#@$][A-Z0-9#@$]{0,7}){0,21}$")
JOBNAME = re.compile(r"^[A-Z#@$][A-Z0-9#@$]{0,7}$")

# Verbs the source lane may use. Read-only, and the list is closed.
SOURCE_VERBS = frozenset({"observe", "retrieve", "list"})
TARGET_VERBS = frozenset({"submit", "observe", "retrieve", "list"})


class PackError(ValueError):
    """A pack that would be unsafe or ambiguous to execute."""


@dataclass(frozen=True)
class Comparison:
    """One pair of outputs to compare, and how."""
    dataset: str
    kind: str = "sequence"          # sequence | set | summary
    normalize: tuple[str, ...] = ()  # ledger entry ids that may apply
    key: tuple[str, ...] = ()        # fields identifying a record, for set kind


@dataclass(frozen=True)
class Job:
    id: str
    jobname: str
    inputs: tuple[str, ...]
    compare: tuple[Comparison, ...]
    description: str = ""


@dataclass(frozen=True)
class JobPack:
    pack_id: str
    estate: str
    jobs: tuple[Job, ...]
    source: Mapping[str, Any] = field(default_factory=dict)
    target: Mapping[str, Any] = field(default_factory=dict)

    @property
    def comparisons(self) -> int:
        return sum(len(job.compare) for job in self.jobs)


# ── validation ───────────────────────────────────────────────────────────
def validate_pack(raw: Mapping[str, Any]) -> JobPack:
    """Parse and refuse. Every rejection names what to fix.

    The source lane is checked hardest: a pack that asks the legacy system to
    run anything is refused here, so the read-only posture is a property of the
    loader rather than a convention the caller is trusted to keep.
    """
    if raw.get("pack_type") != PACK_TYPE:
        raise PackError(f"pack_type must be {PACK_TYPE!r}")
    if raw.get("schema_version") != SCHEMA_VERSION:
        raise PackError(f"schema_version must be {SCHEMA_VERSION!r}")

    pack_id = str(raw.get("pack_id", "")).strip()
    if not pack_id:
        raise PackError("pack_id is required")

    source = dict(raw.get("source") or {})
    target = dict(raw.get("target") or {})
    _check_lane("source", source, SOURCE_VERBS)
    _check_lane("target", target, TARGET_VERBS)

    jobs_raw = raw.get("jobs") or []
    if not jobs_raw:
        raise PackError("a pack with no jobs would verify nothing")

    jobs, seen = [], set()
    for entry in jobs_raw:
        job = _job(entry)
        if job.id in seen:
            raise PackError(f"duplicate job id {job.id!r}")
        seen.add(job.id)
        jobs.append(job)

    return JobPack(pack_id=pack_id, estate=str(raw.get("estate", "")),
                   jobs=tuple(jobs), source=source, target=target)


def _check_lane(name: str, lane: Mapping[str, Any], allowed: frozenset[str]) -> None:
    if not lane:
        raise PackError(f"{name} lane is required")
    verbs = set(lane.get("verbs") or [])
    if not verbs:
        raise PackError(f"{name} lane must declare its verbs")
    forbidden = verbs - allowed
    if forbidden:
        raise PackError(
            f"{name} lane may not use {sorted(forbidden)}. "
            f"Allowed: {sorted(allowed)}. The legacy system is observed, never driven."
        )


def _job(entry: Mapping[str, Any]) -> Job:
    identifier = str(entry.get("id", "")).strip()
    if not identifier:
        raise PackError("every job needs an id")
    jobname = str(entry.get("jobname", "")).strip().upper()
    if not JOBNAME.match(jobname):
        raise PackError(f"{identifier}: jobname {jobname!r} is not a valid z/OS job name")

    inputs = tuple(str(d).strip().upper() for d in (entry.get("inputs") or []))
    for dataset in inputs:
        if not DATASET.match(dataset):
            raise PackError(f"{identifier}: input {dataset!r} is not a valid dataset name")

    compares = entry.get("compare") or []
    if not compares:
        raise PackError(f"{identifier}: a job with nothing to compare proves nothing")

    parsed = []
    for item in compares:
        dataset = str(item.get("dataset", "")).strip().upper()
        if not DATASET.match(dataset):
            raise PackError(f"{identifier}: compare target {dataset!r} is not a valid dataset name")
        kind = str(item.get("kind", "sequence"))
        if kind not in {"sequence", "set", "summary"}:
            raise PackError(f"{identifier}: compare kind {kind!r} is not one of sequence, set, summary")
        key = tuple(str(k) for k in (item.get("key") or ()))
        if kind == "set" and not key:
            raise PackError(f"{identifier}: a set comparison needs a key, or record order "
                            "would be silently ignored")
        parsed.append(Comparison(dataset=dataset, kind=kind, key=key,
                                 normalize=tuple(str(n) for n in (item.get("normalize") or ()))))

    return Job(id=identifier, jobname=jobname, inputs=inputs,
               compare=tuple(parsed), description=str(entry.get("description", "")))


# ── lanes ────────────────────────────────────────────────────────────────
class Reader(Protocol):
    """Whatever can fetch a job and a dataset. z/OSMF in production."""
    def job(self, jobname: str, job_id: str | None = None) -> Mapping[str, Any]: ...
    def dataset(self, name: str) -> bytes: ...


class SourceLane:
    """The legacy system. Observed only.

    There is deliberately no submit method. The read-only guarantee is the
    absence of a capability, not a flag someone can set.
    """

    def __init__(self, reader: Reader):
        self._reader = reader

    def observe(self, job: Job) -> dict:
        record = self._reader.job(job.jobname)
        return {
            "lane": "source",
            "job": job.id,
            "jobname": job.jobname,
            "run": record.get("jobid"),
            "completed": record.get("retcode"),
            "outputs": {c.dataset: self._reader.dataset(c.dataset) for c in job.compare},
            "submitted_by_us": False,
            "evidence_class": _evidence_class(record),
            "evidence": record.get("bundle"),
        }


class TargetLane:
    """The converted application. Replayed."""

    def __init__(self, reader: Reader, submit):
        self._reader = reader
        self._submit = submit

    def replay(self, job: Job, source_run: Mapping[str, Any]) -> dict:
        source_class = _evidence_class(source_run)
        handle = self._submit(job.jobname, list(job.inputs))
        record = self._reader.job(job.jobname, handle)
        target_class = _evidence_class(record)
        return {
            "lane": "target",
            "job": job.id,
            "jobname": job.jobname,
            "run": handle,
            "completed": record.get("retcode"),
            "outputs": {c.dataset: self._reader.dataset(c.dataset) for c in job.compare},
            "replayed_from": source_run.get("run"),
            "submitted_by_us": True,
            "source_evidence_class": source_class,
            "target_evidence_class": target_class,
            "evidence_class": evidence_floor(source_class, target_class),
            "evidence": record.get("bundle"),
        }


def _evidence_class(record: Mapping[str, Any]) -> str:
    # Unlabelled fixture readers must never acquire an observed claim.
    value = record.get("evidence_class", "simulated")
    if value not in ("simulated", "local_observed", "zos_observed"):
        raise PackError("Unsupported reader evidence_class")
    return value


# ── the run ──────────────────────────────────────────────────────────────
def plan(pack: JobPack) -> dict:
    """What this pack would do, without doing any of it.

    Worth running before a customer approves access. It states exactly which
    datasets are read, which job is submitted where, and what is compared.
    """
    _check_lane("source", pack.source, SOURCE_VERBS)
    _check_lane("target", pack.target, TARGET_VERBS)
    return {
        "pack_id": pack.pack_id,
        "estate": pack.estate,
        "jobs": len(pack.jobs),
        "comparisons": pack.comparisons,
        "source_reads": sorted({c.dataset for j in pack.jobs for c in j.compare}
                               | {d for j in pack.jobs for d in j.inputs}),
        "source_submits": sorted({j.jobname for j in pack.jobs if "submit" in pack.source["verbs"]}),
        "target_submits": sorted({j.jobname for j in pack.jobs if "submit" in pack.target["verbs"]}),
        "normalization_referenced": sorted({n for j in pack.jobs
                                            for c in j.compare for n in c.normalize}),
    }


def load(path: str | Path) -> JobPack:
    return validate_pack(json.loads(Path(path).read_text(encoding="utf-8")))
