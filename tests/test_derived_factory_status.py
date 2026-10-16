import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.release_status_records import load, render
from tools.build_release_packet import build


class DerivedStatusTests(unittest.TestCase):
    def test_changed_measurements_change_both_outputs(self):
        model = load()
        changed = copy.deepcopy(model)
        release = changed["release"]
        release["programs"]["INTCALC"]["business"]["fraction"] = "6/9"
        release["programs"]["INTCALC"]["io"]["fraction"] = "12/17"
        release["raw_kill_rate"] = "41/63"
        release["programs"]["INTCALC"]["diversity"] = {"fixture": 13}
        release["scopes"]["twin"]["projected"]["kill_rate"] = "41/42"
        changed["activation"]["signed_only"] = False
        value, text = render(changed)
        for expected in ("6/9", "12/17", "41/63", "41/42", "| fixture | 13 |"):
            self.assertIn(expected, text)
        self.assertFalse(value["factory_activated"])
        self.assertNotEqual(render(model), (value, text))
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root/"docs/factory").mkdir(parents=True)
            with patch("tools.build_release_packet.load", return_value=changed):
                build(root=root)
            packet = next((root/"docs/factory").glob("howard-decision-packet-*.md")).read_text()
            for expected in ("6/9", "12/17", "41/63", "41/42"):
                self.assertIn(expected, packet)
