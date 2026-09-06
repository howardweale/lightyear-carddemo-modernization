from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/cloudbank_operational_baseline.py"
SPEC = importlib.util.spec_from_file_location("cloudbank_operational_baseline", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class Client:
    project = "test-project"

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, endpoint, params, body=None):
        self.calls.append((endpoint, params, body))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class OperationalBaselineTests(unittest.TestCase):
    def test_complete_trace_scan_recognizes_every_service_once(self):
        traces = [{"traceId": f"{index:032x}",
                   "spans": [{"labels": {"service.name": service, "ignored": "value"}}]}
                  for index, service in enumerate(MODULE.SERVICES, 1)]
        client = Client([{"traces": traces}])
        result = MODULE.service_traces(client, "2026-09-06T21:00:00Z", "2026-09-06T22:00:00Z")
        self.assertEqual("observed", result["status"])
        self.assertEqual(set(MODULE.SERVICES), set(result["services"]))
        self.assertEqual(1, len(client.calls))
        endpoint, params, _ = client.calls[0]
        self.assertEqual("traces", endpoint)
        self.assertEqual("COMPLETE", params["view"])
        self.assertEqual("traces(traceId,spans(labels)),nextPageToken", params["fields"])
        self.assertTrue(all("trace_identity_sha256" in row
                            and "trace_id" not in row for row in result["services"].values()))

    def test_trace_access_denial_is_inconclusive_not_absent(self):
        denied = MODULE.ObservationError("google-api-http-error", 403,
                                         {"status": "PERMISSION_DENIED"})
        result = MODULE.service_traces(Client([denied]), "start", "end")
        self.assertEqual("incomplete", result["status"])
        first = result["services"][MODULE.SERVICES[0]]
        self.assertEqual(403, first["code"])
        self.assertEqual("PERMISSION_DENIED", first["api_error"]["status"])
        self.assertTrue(all(row["status"] == "inconclusive"
                            for row in result["services"].values()))

    def test_log_probe_reads_metadata_only_and_checks_resource_identity(self):
        entry = {"timestamp": "2026-09-06T22:00:00Z", "insertId": "one",
                 "resource": {"type": "k8s_container", "labels": {
                     "project_id": "test-project", "cluster_name": "test-cluster",
                     "namespace_name": "test-ns", "container_name": "account"}}}
        client = Client([{"entries": [entry]}])
        result = MODULE.log_probe(client, "account", "start", "end",
                                  project="test-project", cluster="test-cluster",
                                  namespace="test-ns")
        self.assertEqual("observed", result["status"])
        self.assertNotIn("textPayload", client.calls[0][1]["fields"])
        self.assertNotIn("jsonPayload", client.calls[0][1]["fields"])

    def test_safe_api_error_excludes_free_text(self):
        payload = {"error": {"status": "PERMISSION_DENIED", "message": "secret text",
            "details": [{"@type": "type.googleapis.com/google.rpc.ErrorInfo",
                         "reason": "IAM_PERMISSION_DENIED", "domain": "googleapis.com",
                         "metadata": {"service": "cloudtrace.googleapis.com",
                                      "permission": "cloudtrace.traces.list",
                                      "unsafe": "secret"}}]}}
        result = MODULE.safe_api_error(json.dumps(payload).encode())
        self.assertEqual("PERMISSION_DENIED", result["status"])
        self.assertNotIn("message", result)
        self.assertNotIn("unsafe", result["error_info"][0]["metadata"])

    def test_metric_identity_requires_workload_type_and_known_service(self):
        series = {"metric": {"type": "workload.googleapis.com/jvm.thread.count",
                             "labels": {"service_name": "account"}}}
        self.assertEqual("account", MODULE.metric_service(series))
        series["metric"]["type"] = "custom.googleapis.com/jvm.thread.count"
        self.assertIsNone(MODULE.metric_service(series))


if __name__ == "__main__":
    unittest.main()
