"""Observation-only binding of job packs to the existing JES collector.

Dataset names require explicit bindings to retained spool DDs, separate from
the qualified graph mapping. Catalogued MVS datasets are not silently replaced
by spool text or read from their current, potentially unrelated contents.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
import json
from pathlib import Path
from typing import Any, Mapping

from lightyear_runtime.zosmf import ZosmfClient, ZosmfConfig, ZosmfError, ZosmfJobsAdapter
from .batch_pack import DATASET, JOBNAME


class ZosmfReader:
    """Read completed jobs and explicitly bound spool outputs; never submit."""

    def __init__(self, client: ZosmfClient, config: ZosmfConfig, mapping_path: Path,
                 *, attest_real_zos: bool = False, owner: str = "*",
                 datasets: Mapping[str, Mapping[str, str]] | None = None):
        config.validate()
        if type(attest_real_zos) is not bool:
            raise ZosmfError("attest_real_zos must be an explicit boolean")
        if attest_real_zos and not config.can_attest_real_zos:
            raise ZosmfError("Real z/OS attestation requires verified HTTPS on a non-loopback host")
        self._client, self._config = client, config
        self._mapping_path = Path(mapping_path)
        self._mapping = json.loads(self._mapping_path.read_text(encoding="utf-8"))
        self._datasets = {name: dict(binding) for name, binding in (datasets or {}).items()}
        self._attest, self._owner = attest_real_zos, owner
        self._selected: tuple[str, str] | None = None

    @staticmethod
    def _completed(record: dict[str, Any]) -> datetime:
        if record.get("status") != "OUTPUT" or not record.get("retcode"):
            raise ZosmfError("A completed job with a return code is required")
        try:
            ended = datetime.fromisoformat(record["exec-ended"].replace("Z", "+00:00"))
            if ended.tzinfo is None:
                raise ValueError("Missing timezone")
            return ended
        except (KeyError, TypeError, AttributeError, ValueError) as exc:
            raise ZosmfError("Completed job requires an unambiguous exec-ended timestamp") from exc

    def job(self, jobname: str, job_id: str | None = None) -> dict:
        self._selected = None  # Failed selection must not leave a previous job readable.
        if not isinstance(jobname, str) or not JOBNAME.fullmatch(jobname):
            raise ZosmfError("Invalid exact job name")
        if self._mapping.get("job", {}).get("name") != jobname:
            raise ZosmfError("Job name does not match the graph mapping")
        if job_id is None:
            jobs = self._client.list_jobs(self._owner, jobname, max_jobs=1000)
            if len(jobs) >= 1000:
                raise ZosmfError("Job listing may be truncated; supply an explicit job ID")
            candidates = []
            for item in jobs:
                if item.get("jobname") == jobname and item.get("status") == "OUTPUT":
                    candidates.append((self._completed(item), item))
            if not candidates:
                raise ZosmfError("No completed run exists for this job")
            latest = max(ended for ended, _ in candidates)
            matches = [item for ended, item in candidates if ended == latest]
            if len(matches) != 1:
                raise ZosmfError("Latest completed run is ambiguous; supply an explicit job ID")
            job_id = matches[0].get("jobid")
        if not isinstance(job_id, str) or not job_id:
            raise ZosmfError("Completed job has no valid job ID")
        adapter = ZosmfJobsAdapter(self._client, self._config, self._mapping_path,
                                  jobname, job_id, attest_real_zos=self._attest)
        bundle = adapter.capture()
        details = next(item.details for item in bundle.observations if item.operation == "job_completed")
        self._completed({"status": details["status"], "retcode": details["return_code"],
                         "exec-ended": details["exec_ended"]})
        if any(item.evidence_class != adapter.evidence_class for item in bundle.observations):
            raise ZosmfError("Collector evidence class is inconsistent")
        self._selected = (jobname, job_id)
        return {"jobid": job_id, "retcode": details["return_code"],
                "evidence_class": adapter.evidence_class, "bundle": asdict(bundle)}

    def dataset(self, name: str) -> bytes:
        if not self._selected:
            raise ZosmfError("Select a completed job before reading its outputs")
        if not isinstance(name, str) or not DATASET.fullmatch(name) or len(name) > 44:
            raise ZosmfError("Invalid dataset name")
        binding = self._datasets.get(name)
        if not isinstance(binding, dict) or not binding.get("ddname") or not binding.get("stepname"):
            raise ZosmfError("Dataset needs an explicit spool ddname and stepname binding")
        jobname, job_id = self._selected
        files = self._client.spool_files(jobname, job_id)
        matches = [item for item in files if item.get("ddname") == binding["ddname"]
                   and item.get("stepname") == binding["stepname"]
                   and item.get("procstep") == binding.get("procstep")]
        if len(matches) != 1:
            raise ZosmfError("Dataset spool binding is missing or ambiguous")
        item = matches[0]
        if item.get("jobname") != jobname or item.get("jobid") != job_id:
            raise ZosmfError("Dataset spool belongs to a different job")
        if type(item.get("id")) is not int or item["id"] < 0:
            raise ZosmfError("Dataset spool requires an integer file ID")
        if type(item.get("record-count")) is not int or not 0 <= item["record-count"] <= 5000:
            raise ZosmfError("Dataset spool record count is unknown or exceeds the read bound")
        return self._client.spool_records(jobname, job_id, item["id"])
