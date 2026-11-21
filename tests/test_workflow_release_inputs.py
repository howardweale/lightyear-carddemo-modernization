from contextlib import redirect_stderr, redirect_stdout
from email.message import Message
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import subprocess
import textwrap
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from urllib.request import Request

from tools.ci import github_read_budget as net
from tools.ci import workflow_release_inputs as inputs


URL = "https://github.com/howardweale/lightyear-carddemo-modernization/releases/download/test/data.json"
CDN = "https://release-assets.githubusercontent.com/test"


class Response(io.BytesIO):
    status = 200

    def geturl(self):
        return CDN


def denied(status, headers=None, body=b"", url=URL):
    h = Message()
    for k, v in (headers or {}).items():
        h[k] = v
    return HTTPError(url, status, "test", h, io.BytesIO(body))


class BudgetTests(unittest.TestCase):
    def make(self, *items):
        self.left, self.calls, self.sleeps = list(items), [], []
        self.now = 0

        def read(request, timeout):
            self.calls.append(request)
            self.assertLessEqual(timeout, 25)
            result = self.left.pop(0)
            if isinstance(result, BaseException):
                raise result
            return Response(result)

        def sleep(value):
            self.now += value
            self.sleeps.append(value)

        return net.ReadBudget(open_request=read, monotonic=lambda: self.now,
                              wall=lambda: 100 + self.now, sleep=sleep, jitter=lambda: 0)

    def test_429_honors_retry_after_and_sends_no_authority(self):
        read = self.make(denied(429, {"Retry-After": "5"}), b"data")
        self.assertEqual(read.get(URL, 4), b"data")
        self.assertEqual(self.sleeps, [5])
        self.assertTrue(all(call.get_method() == "GET" and call.get_header("Authorization") is None
                            for call in self.calls))

    def test_primary_403_waits_for_later_of_reset_and_retry_after(self):
        read = self.make(denied(403, {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "110",
                                      "Retry-After": "5"}), b"x")
        self.assertEqual(read.get(URL, 1), b"x")
        self.assertEqual(self.sleeps, [10])

    def test_secondary_limit_uses_60_seconds_without_instructions(self):
        body = b'{"message":"You have exceeded a secondary rate limit. Wait and retry."}'
        read = self.make(denied(403, body=body), b"x")
        self.assertEqual(read.get(URL, 1), b"x")
        self.assertEqual(self.sleeps, [60])

    def test_permission_denial_or_404_is_permanent(self):
        for status in (401, 403, 404, 410, 500):
            with self.subTest(status=status):
                read = self.make(denied(status, {"Retry-After": "5"}, b'{"message":"Resource not accessible"}'))
                with self.assertRaisesRegex(net.ReadRefused, "release-http-status"):
                    read.get(URL, 1)
                self.assertFalse(self.sleeps)

    def test_cdn_403_cannot_impersonate_github_api(self):
        read = self.make(denied(403, {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "103"}, url=CDN))
        with self.assertRaisesRegex(net.ReadRefused, "release-http-status"):
            read.get(URL, 1)
        self.assertEqual(len(self.calls), 1)

    def test_retry_after_date_and_invalid_value(self):
        self.assertEqual(net.seconds("Thu, 01 Jan 1970 00:01:45 GMT", 100), 5)
        with self.assertRaisesRegex(net.ReadRefused, "release-retry-after"):
            net.seconds("tomorrow", 100)

    def test_no_truncation_of_oversize_delay(self):
        read = self.make(denied(429, {"Retry-After": "76"}))
        with self.assertRaisesRegex(net.ReadRefused, "release-rate-budget"):
            read.get(URL, 1)
        self.assertEqual(self.sleeps, [])

    def test_three_attempts_maximum(self):
        read = self.make(*(denied(429, {"Retry-After": "1"}) for _ in range(3)))
        with self.assertRaisesRegex(net.ReadRefused, "release-rate-budget"):
            read.get(URL, 1)
        self.assertEqual(len(self.calls), 3)
        self.assertEqual(self.sleeps, [1, 2])

    def test_elapsed_sleep_budget_shared_between_assets(self):
        read = self.make(denied(429, {"Retry-After": "50"}), b"x", denied(429, {"Retry-After": "26"}))
        self.assertEqual(read.get(URL, 1), b"x")
        with self.assertRaisesRegex(net.ReadRefused, "release-rate-budget"):
            read.get(URL, 1)
        self.assertEqual(self.sleeps, [50])

    def test_no_attempt_after_deadline(self):
        read = self.make()
        self.now = 165
        with self.assertRaisesRegex(net.ReadRefused, "release-deadline"):
            read.get(URL, 1)
        self.assertFalse(self.calls)

    def test_transport_and_short_long_bodies_refuse(self):
        for value in (URLError("test"), b"", b"xx"):
            read = self.make(value)
            with self.assertRaises(net.ReadRefused):
                read.get(URL, 1)
            self.assertEqual(len(self.calls), 1)

    def test_origin_and_redirect_boundaries(self):
        for target in ("http://github.com/x", "https://user@github.com/x", "https://github.com:443/x",
                       URL+"?operator=1", URL.replace("howardweale", "other"), "https://example.org/x"):
            with self.subTest(target=target), self.assertRaises(net.ReadRefused):
                self.make().get(target, 1)
        redirect = net.ReleaseRedirects()
        self.assertEqual(redirect.redirect_request(Request(URL), None, 302, "", {}, CDN).full_url, CDN)
        with self.assertRaises(net.ReadRefused):
            redirect.redirect_request(Request(URL), None, 302, "", {}, "https://evil.invalid/x")


class PublicInputsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "inputs"
        self.env = dict(GITHUB_REPOSITORY=inputs.REPOSITORY,
                        GITHUB_WORKFLOW_REF=inputs.REPOSITORY+"/.github/workflows/test.yml@refs/pull/1/merge",
                        GITHUB_SHA="1"*40, GITHUB_RUN_ID="123", GITHUB_RUN_ATTEMPT="1")
        self.profile = "fixture"
        self.raw = b"public"
        pin = (len(self.raw), hashlib.sha256(self.raw).hexdigest())
        patcher = patch.dict(inputs.PROFILES, {self.profile: ("test.yml", "test", {"a.txt": pin})})
        patcher.start()
        self.addCleanup(patcher.stop)

    def produce(self, raw=None):
        class Reader:
            def get(inner, url, size):
                self.assertEqual(url, "https://github.com/" + inputs.REPOSITORY + "/releases/download/test/a.txt")
                return self.raw if raw is None else raw
        return inputs.produce(self.path, self.profile, self.env, Reader())

    def test_exact_bytes_and_reuse_from_successful_prior_attempt(self):
        inputs.precheck(self.path, "19", "1", self.profile, self.env)
        self.assertEqual(self.produce(), "1")
        inputs.verify(self.path, self.profile, "1", dict(self.env, GITHUB_RUN_ATTEMPT="2"))

    def test_integrity_failures_do_not_issue_a_receipt(self):
        with self.assertRaisesRegex(net.ReadRefused, "release-member-hash"):
            self.produce(b"PUBLIC")
        self.assertFalse((self.path / inputs.RECEIPT).exists())

    def test_output_is_exclusive(self):
        self.produce()
        with self.assertRaisesRegex(net.ReadRefused, "release-output-exists"):
            self.produce()

    def test_extra_missing_or_changed_file(self):
        self.produce()
        extra = self.path / "extra"
        extra.write_bytes(b"x")
        with self.assertRaisesRegex(net.ReadRefused, "release-member-set"):
            inputs.verify(self.path, self.profile, "1", self.env)
        extra.unlink()
        f = self.path / "a.txt"
        f.write_bytes(b"PUBLIC")
        with self.assertRaisesRegex(net.ReadRefused, "release-member-hash"):
            inputs.verify(self.path, self.profile, "1", self.env)
        f.unlink()
        with self.assertRaisesRegex(net.ReadRefused, "release-member-set"):
            inputs.verify(self.path, self.profile, "1", self.env)

    def test_foreign_run_head_workflow_and_attempt_refuse(self):
        self.produce()
        for name, val in (("GITHUB_RUN_ID","124"), ("GITHUB_SHA","2"*40),
                          ("GITHUB_WORKFLOW_REF",inputs.REPOSITORY+"/.github/workflows/other.yml@refs/heads/main")):
            with self.subTest(name=name), self.assertRaises(net.ReadRefused):
                inputs.verify(self.path, self.profile, "1", dict(self.env, **{name:val}))
        with self.assertRaises(net.ReadRefused):
            inputs.verify(self.path, self.profile, "2", self.env)

    def test_bad_or_missing_artifact_id_refuses_before_download(self):
        for identifier in ("", "0", "1,2", "all", "01"):
            with self.subTest(identifier=identifier), self.assertRaisesRegex(net.ReadRefused, "release-id"):
                inputs.precheck(self.path, identifier, "1", self.profile, self.env)

    def test_manifest_alone_does_not_authorize_bytes(self):
        self.produce()
        forged = self.path / inputs.RECEIPT
        descriptor = json.loads(forged.read_bytes())
        descriptor["members"]["a.txt"]["sha256"] = hashlib.sha256(b"FORGED").hexdigest()
        (self.path / "a.txt").write_bytes(b"FORGED")
        forged.write_bytes((json.dumps(descriptor,sort_keys=True,separators=(",",":"))+"\n").encode())
        with self.assertRaisesRegex(net.ReadRefused,"release-member-hash"):
            inputs.verify(self.path, self.profile,"1",self.env)

    def test_cli_reports_only_fixed_code_for_missing_receipt(self):
        with patch.dict(os.environ, self.env, clear=True), redirect_stderr(io.StringIO()) as err:
            result = inputs.main(["verify", "codecs", str(self.path)])
        self.assertEqual(result, 2)
        self.assertEqual(err.getvalue().strip(), "release-input-unavailable")


class WorkflowTests(unittest.TestCase):
    matrix_jobs = {"cobol-codecs": 2, "intcalc-preview-composition": 3,
                   "intcalc-graph-repair-controller": 2, "required-ci": 2,
                   "copau-run-boundary": 2, "verify-graph-retention": 1}

    def workflow(self, name):
        return Path(".github/workflows", name+".yml").read_text(encoding="utf-8")

    def test_quota_brackets_each_job_in_all_six_workflows(self):
        for name, job_definitions in self.matrix_jobs.items():
            source = self.workflow(name)
            with self.subTest(name=name):
                self.assertEqual(source.count("QUOTA_PHASE: start"), job_definitions)
                self.assertEqual(source.count("QUOTA_PHASE: end"), job_definitions)
                self.assertEqual(source.count("name: Record GitHub quota at job end\n        if: always()"), job_definitions)
                self.assertEqual(source.count("gh\", \"api\", \"--include\", \"rate_limit"), 1)
                self.assertIn("python -I -B -", source)
                self.assertNotIn("GH_DEBUG", source)

    def test_scoped_producer_and_consumers(self):
        for name in ("cobol-codecs","intcalc-preview-composition","intcalc-graph-repair-controller"):
            src = self.workflow(name)
            with self.subTest(name=name):
                self.assertNotIn("gh release download", src)
                self.assertEqual(src.count("id: fetch\n"), 1)
                self.assertIn("needs: release-inputs", src)
                self.assertEqual(src.count("artifact-ids: ${{ needs.release-inputs.outputs.artifact_id }}"), 1)
                self.assertLess(src.index("Check producer identity"), src.index("Retrieve exact run-scoped public inputs"))
                self.assertLess(src.index("Retrieve exact run-scoped public inputs"), src.index("Verify producer receipt"))

    def test_quota_sampler_handles_shared_headers_and_missing_values(self):
        src = self.workflow("verify-graph-retention")
        script = textwrap.dedent(src.split("python -I -B - <<'PY'\n",1)[1].split("\n          PY",1)[0])
        with tempfile.TemporaryDirectory() as tmp:
            env = dict(QUOTA_PHASE="start",GITHUB_JOB="retain",RUNNER_OS="Linux",RUNNER_ARCH="X64",
                       GITHUB_RUN_ID="1",GITHUB_RUN_ATTEMPT="1",GITHUB_STEP_SUMMARY=str(Path(tmp)/"summary"))
            for headers, expected in [(b"x-ratelimit-used: 25\r\nx-ratelimit-remaining: 75\r\nx-ratelimit-reset: 123",
                                       "status=observed used=25 remaining=75 reset=123"),
                                      (b"x-ratelimit-used: 25", "status=unavailable")]:
                raw = b"HTTP/2.0 200 OK\r\n" + headers + b"\r\n\r\nPRIVATE BODY"
                with patch.dict(os.environ,env), patch.object(subprocess,"run",return_value=subprocess.CompletedProcess([],0,stdout=raw)), redirect_stdout(io.StringIO()) as log:
                    exec(compile(script, "<quota-sampler>", "exec"), {})
                self.assertIn(expected, log.getvalue())
                self.assertNotIn("PRIVATE",log.getvalue())
