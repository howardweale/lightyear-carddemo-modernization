"""Exercise tested_source through the real download route dispatcher; no service writes."""
import base64
import io
import unittest
import zipfile
from unittest.mock import patch
from tools.carddemo_release_retention import Github, REPO
from tools.ci.verify_graph_retention import tested_source


class RetentionAttemptLogRoute(unittest.TestCase):
    def test_exact_attempt_route_uses_json_accept(self):
        route = "actions/runs/41137555085/attempts/1/logs"
        with patch("tools.carddemo_release_retention.subprocess.check_output", return_value=b"zip") as call:
            self.assertEqual(Github().download(route), b"zip")
        call.assert_called_once_with(["gh", "api", "repos/" + REPO + "/" + route,
                                      "-H", "Accept: application/json"])

    def test_existing_download_headers_remain_distinct(self):
        for route, accept in (("actions/artifacts/123/zip", "application/json"),
                              ("releases/assets/456", "application/octet-stream")):
            with self.subTest(route=route), patch(
                    "tools.carddemo_release_retention.subprocess.check_output", return_value=b"x") as call:
                Github().download(route)
                self.assertEqual(call.call_args.args[0][-1], "Accept: " + accept)

    def test_other_routes_refuse_before_subprocess(self):
        routes = ["actions/runs/1/logs", "actions/runs/1/attempts/0/logs",
                  "actions/runs/0/attempts/1/logs", "actions/runs/01/attempts/1/logs",
                  "actions/runs/1/attempts/01/logs", "actions/runs/1/attempts/1/logs?x=1",
                  "actions/runs/1/attempts/1/logs/extra", "actions/runs/1/attempts/1/jobs",
                  "https://api.github.com/actions/runs/1/attempts/1/logs",
                  "actions/runs/1/attempts/1/logs\n"]
        for route in routes:
            with self.subTest(route=route), patch(
                    "tools.carddemo_release_retention.subprocess.check_output") as call:
                with self.assertRaises(ValueError):
                    Github().download(route)
                call.assert_not_called()

    def test_tested_source_reaches_real_dispatcher_and_checks_source(self):
        head, base, merge = "a" * 40, "b" * 40, "c" * 40
        workflow = b"name: frozen producer\n"
        run = dict(id=123, run_attempt=1, event="pull_request", head_sha=head,
                   path=".github/workflows/lightyear-verify-mcp.yml")
        job = dict(steps=[dict(number=2, name="Run actions/checkout@v7",
                              status="completed", conclusion="success")])
        lines = ["  ref: " + merge, "[command]/usr/bin/git checkout --progress --force " + merge,
                 "[command]/usr/bin/git log -1 --format=%H", merge]
        raw = "".join("2026-10-30T20:13:20.0570304Z " + line + "\n" for line in lines).encode()
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w") as output:
            output.writestr("isolated-judge/2_Run actions_checkout@v7.txt", raw)
        responses = [dict(sha=merge, parents=[dict(sha=base), dict(sha=head)]),
                     dict(type="file", path=run["path"], encoding="base64", size=len(workflow),
                          content=base64.b64encode(workflow).decode())]
        with patch("tools.carddemo_release_retention.subprocess.check_output",
                   return_value=archive.getvalue()) as download, patch.object(
                       Github, "api", side_effect=responses) as api, patch(
                           "pathlib.Path.read_bytes", return_value=workflow):
            self.assertEqual(tested_source(Github(), run, job), merge)
        self.assertEqual(download.call_args.args[0][2],
                         "repos/" + REPO + "/actions/runs/123/attempts/1/logs")
        self.assertEqual(api.call_args_list[0].args, ("git/commits/" + merge,))
        self.assertEqual(api.call_args_list[1].args, ("contents/" + run["path"] + "?ref=" + merge,))
