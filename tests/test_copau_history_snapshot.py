from copy import deepcopy
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import Mock
from zipfile import ZipFile

from tools.ci import copau_history_snapshot as h
from tools.copau_private_prerequisites import Refused


class HistoricalSnapshotTests(TestCase):
    def setUp(self):
        self.commit = "a"*40
        self.now = datetime(2030, 5, 1, tzinfo=timezone.utc)
        self.env = dict(GITHUB_EVENT_NAME="push", GITHUB_REF="refs/heads/main",
                        GITHUB_WORKFLOW_REF=f"{h.REPO}/.github/workflows/{h.WORKFLOW}@refs/heads/main", GITHUB_REPOSITORY=h.REPO,
                        GITHUB_SHA=self.commit, GITHUB_RUN_ATTEMPT="1", GITHUB_RUN_ID="42")
        self.folder = TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.out = Path(self.folder.name)
        self.history = h.absent()
        self.history["missing"] = [dict(kind="artifact",id=7),dict(kind="unknown-history",id=h.UNKNOWN)]
        self.history["catalog"] = [dict(kind="artifact",id=7)]
        self.history.update(observed_count=1, metadata_error_count=0,
                            catalog_sha256=h.sha(h.encoded(self.history["catalog"])))
        self.scan = Mock(return_value=self.history)

    def capture(self):
        hist, obs = h.capture(self.commit,self.out,self.scan,env=self.env,clock=lambda:self.now)
        return hist, obs, h.load_json((self.out/h.MEMBER).read_bytes())

    def test_main_collects_once_child_reuses_identical_history(self):
        hist,obs,snap = self.capture()
        rows,later = h.reuse(dict(historical=hist,historical_observation=obs),self.commit,
                             self.now+timedelta(seconds=9))
        self.scan.assert_called_once_with()
        self.assertEqual(rows,self.history)
        self.assertEqual(later["age_seconds"],9)
        self.assertEqual(later["observation_sha256"],h.sha(h.encoded(snap)))
        self.assertEqual(later["capture_start"],later["capture_end"])

    def test_even_on_main_observation_cannot_be_overwritten(self):
        self.capture()
        with self.assertRaises(Refused):
            self.capture()
        self.scan.assert_called_once_with()

    def test_pr_and_rerun_never_enumerate(self):
        hist,_,snap = self.capture()
        for mutation in (dict(GITHUB_RUN_ATTEMPT="2"),dict(GITHUB_EVENT_NAME="pull_request"),
                         dict(GITHUB_SHA="b"*40),dict(GITHUB_REPOSITORY="fork/repo"), dict(GITHUB_WORKFLOW_REF="other")):
            with self.subTest(mutation=mutation):
                with self.assertRaises(Refused):
                    h.capture(self.commit, self.out / "unused", self.scan, env=dict(self.env, **mutation))
                rows, obs = h.observe(self.commit, fetch=lambda _:snap, clock=lambda:self.now)
                self.assertEqual(rows,hist)
                self.assertEqual(obs["producer_attempt"],1)
        self.scan.assert_called_once_with()

    def test_absence_has_no_invented_age_or_capture_interval(self):
        rows,obs=h.observe(self.commit,fetch=Mock(side_effect=h.Unavailable),
                           clock=lambda:self.now)
        self.assertIsNone(obs["age_seconds"])
        self.assertIsNone(obs["capture_end"])
        self.assertEqual(rows["missing"],[dict(kind="unknown-history",id=x) for x in (h.UNKNOWN,h.GAP)])
        self.assertEqual(h.reuse(dict(historical=rows,historical_observation=obs),
                                 self.commit,self.now)[0],rows)
        self.scan.assert_not_called()

    def test_partial_scan_preserves_known_and_unknown(self):
        self.history["metadata_error_count"]=1
        self.history["missing"].append(dict(kind="unknown-history",id="release-catalog-unavailable"))
        rows,obs,_=self.capture()
        self.assertEqual(obs["status"],"observed")
        self.assertEqual(rows,self.history)

    def test_bad_join_or_removed_unknown_marker_refuses(self):
        hist,obs,_=self.capture()
        for key,value in (("main_commit","f"*40),("age_seconds",20),("observation_sha256","b"*64)):
            with self.subTest(key=key),self.assertRaises(Refused):
                h.reuse(dict(historical=hist,historical_observation=dict(obs,**{key:value})),
                        self.commit,self.now)
        hist["missing"]=[]
        with self.assertRaises(Refused):
            h.reuse(dict(historical=hist,historical_observation=obs),self.commit,self.now)

    def fake_api(self):
        _,_,snap=self.capture()
        body=BytesIO()
        with ZipFile(body,"w") as archive:
            archive.writestr(h.MEMBER,h.encoded(snap))
        data=body.getvalue()
        run=dict(id=42,head_sha=self.commit,event="push",head_branch="main",
                 path=".github/workflows/"+h.WORKFLOW,
                 repository={"full_name":h.REPO},head_repository={"full_name":h.REPO})
        artifact=dict(id=73,name="copau-catalog-"+self.commit,expired=False,
                      size_in_bytes=len(data),digest="sha256:"+h.sha(data))
        def respond(route):
            if route.startswith("actions/workflows/"):
                return h.encoded(dict(total_count=1,workflow_runs=[run]))
            if route.startswith("actions/runs/42/artifacts?name="):
                return h.encoded(dict(total_count=1,artifacts=[artifact]))
            if route=="actions/artifacts/73/zip":
                return data
            self.fail("unexpected API route")
        return run,artifact,Mock(side_effect=respond),snap

    def test_lookup_is_three_requests_bound_to_producing_run(self):
        _,_,get,snap=self.fake_api()
        self.assertEqual(h.fetch_snapshot(self.commit,get),snap)
        self.assertEqual(get.call_count,3)
        self.assertIn("event=push&head_sha="+self.commit,get.call_args_list[0].args[0])

    def test_pr_wrong_workflow_or_fork_artifact_refuses(self):
        run,_,get,_=self.fake_api()
        original=deepcopy(run)
        for key,value in (("event","pull_request"),("path",".github/workflows/unrelated.yml"),
                          ("head_repository",{"full_name":"fork/other"}),("head_sha","f"*40)):
            with self.subTest(key=key), self.assertRaises(Refused):
                run.update(original)
                run[key]=value
                h.fetch_snapshot(self.commit,get)

    def test_expired_is_a_gap_corrupt_digest_is_a_refusal(self):
        _,artifact,get,_=self.fake_api()
        artifact["expired"]=True
        with self.assertRaises(h.Unavailable):
            h.fetch_snapshot(self.commit,get)
        artifact.update(expired=False,digest="sha256:"+"0"*64)
        with self.assertRaises(Refused):
            h.fetch_snapshot(self.commit,get)

    def test_ambiguous_listing_refuses(self):
        with self.assertRaises(Refused):
            h.listing("unused","artifacts",lambda _:h.encoded(dict(total_count=2,artifacts=[{},{}])))

    def test_future_capture_refuses(self):
        _,_,snap=self.capture()
        with self.assertRaises(Refused):
            h.describe(snap,self.commit,self.now-timedelta(seconds=2))


    def test_exact_age_boundary_and_both_consumer_gaps(self):
        hist, _, snap = self.capture()
        end = self.now + timedelta(seconds=h.MAX_AGE_SECONDS)
        rows, observation = h.observe(self.commit, fetch=lambda _: snap, clock=lambda: end)
        self.assertEqual(observation["status"], "observed")
        self.assertEqual(observation["gaps"], [])
        later = end + timedelta(microseconds=1)
        parent = dict(historical=rows, historical_observation=observation)
        data, child = h.reuse(parent, self.commit, later)
        self.assertEqual(child["status"], "stale")
        self.assertEqual(child["gaps"], [h.STALE_GAP])
        self.assertEqual(child["observation_sha256"], observation["observation_sha256"])
        pr_rows, pr_obs = h.observe(self.commit, fetch=lambda _: snap, clock=lambda: later)
        self.assertEqual((pr_rows, pr_obs), (data, child))
        self.assertEqual(data, hist)
        self.assertIn(dict(kind="artifact", id=7), data["missing"])
        self.assertIn(dict(kind="unknown-history", id=h.UNKNOWN), data["missing"])
        self.scan.assert_called_once_with()

    def test_expired_record_disclosure_survives_child_and_no_age_is_invented(self):
        def expired(_):
            raise h.Unavailable(h.EXPIRED_GAP)
        rows, obs = h.observe(self.commit, fetch=expired, clock=lambda: self.now)
        self.assertEqual(obs["gaps"], [h.EXPIRED_GAP])
        self.assertIsNone(obs["capture_start"])
        self.assertIsNone(obs["age_seconds"])
        self.assertEqual(rows["metadata_error_count"], 1)
        self.assertEqual(h.reuse(dict(historical=rows, historical_observation=obs),
                                 self.commit, self.now), (rows, obs))
        self.scan.assert_not_called()
