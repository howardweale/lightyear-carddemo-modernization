import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from tools import v1_mac_worker as rehearsal


class WorkerRehearsalTests(unittest.TestCase):
    def test_only_dedicated_ids_and_areas(self):
        for identifier in ("prod", "../live", "0"*64):
            with self.assertRaises(ValueError):
                rehearsal.session(identifier,"storage-worker")

    def test_reject_replay_or_symlink_input(self):
        with self.assertRaises(ValueError):
            rehearsal.observed_path(Path("/x/.lightyear-staged-public/authority"))
        with self.assertRaises(ValueError):
            rehearsal.observed_path(Path("../other"))

    def test_changed_staged_public_input_refuses(self):
        with patch.object(rehearsal.staged,"read_owned",return_value=b"fixture"):
            self.assertEqual(rehearsal.checked_bytes(None,rehearsal.sha(b"fixture"),100),b"fixture")
            with self.assertRaises(ValueError):
                rehearsal.checked_bytes(None,"0"*64,100)

    def test_playback_uses_only_frozen_case_identities(self):
        raw=(rehearsal.ROOT/rehearsal.GOOD).read_text(encoding="ascii")
        self.assertEqual(raw.count('case "'),16)
        self.assertIn("unlisted public input",raw)
        self.assertNotIn("java.net.",raw)

    def test_cap_and_timeout_use_different_fixtures(self):
        self.assertIn("Thread.sleep",rehearsal.SLOW)
        self.assertIn("System.out.write",rehearsal.FLOOD)
        self.assertNotEqual(rehearsal.BAD,rehearsal.SLOW)

    def test_vm_space_measured_and_each_minimum_enforced(self):
        with tempfile.TemporaryDirectory() as tmp:
            station=object.__new__(rehearsal.Station)
            station.root=Path(tmp)
            station.docker=["fake"]
            station.config=dict(disk_image=tmp,host_min=1,ledger_min=1,backing_min=1,vm_min=1024)
            with patch.object(rehearsal,"shell",return_value=b"Filesystem 1024-blocks Used Available Capacity Mounted on\noverlay 8 4 4 50% /\n") as command:
                self.assertEqual(station.sample()["available"]["vm"],4096)
                self.assertIn("--network=none",command.call_args.args[0])
                station.config["vm_min"]=4097
                with self.assertRaisesRegex(ValueError,"v1-headroom"):
                    station.sample()

    def test_no_readable_resource_names_in_public_inventory(self):
        station=object.__new__(rehearsal.Station)
        station.docker=["fake"]
        with patch.object(rehearsal,"shell",return_value=b"public-name\n"):
            rows=station.inventory()
        self.assertNotIn("public-name",json.dumps(rows))
        self.assertTrue(all(r["count"]==1 for r in rows.values()))

    def test_negative_cleanup_receipt_is_refused(self):
        row={"removed":[dict(kind=k,absence_confirmed=True) for k in ("volume","container","container")],"cleanup":True}
        self.assertTrue(rehearsal.clean_receipt(row))
        row["removed"][0]["absence_confirmed"]=False
        self.assertFalse(rehearsal.clean_receipt(row))

    def test_sampling_restores_on_operation_fault(self):
        station=object.__new__(rehearsal.Station)
        with patch.object(station,"sample",Mock(return_value={"public":True})) as sample:
            with self.assertRaises(RuntimeError):
                with station.sampling():
                    raise RuntimeError("public fixture")
        self.assertEqual(sample.call_count,2)
