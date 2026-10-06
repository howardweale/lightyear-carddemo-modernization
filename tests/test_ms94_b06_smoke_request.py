import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from lightyear_calibration.contracts import canonical, seal
from tests.test_ms94_a3_entry_v2 import test_signer
from tools.ms94_b06_smoke_request import confirmed_key, published_request


class SmokeRequestTests(unittest.TestCase):
    def test_confirmed_key_is_distinct_and_exact(self):
        tower, campaign = test_signer(), test_signer()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'public.pem'; path.write_bytes(tower.public)
            fingerprint = hashlib.sha256(tower.public).hexdigest()
            self.assertEqual(confirmed_key(path,fingerprint,campaign.public),tower.public)
            with self.assertRaises(ValueError): confirmed_key(path,'0'*64,campaign.public)
            with self.assertRaises(ValueError): confirmed_key(path,fingerprint,tower.public)

    def test_request_requires_exact_public_group_bytes(self):
        group = seal({'snapshot_sha256':'a'*64,'docker_run_window':{},'tower_public_key_sha256':'b'*64})
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'plan.json'; path.write_bytes(canonical(group))
            with patch('tools.ms94_b06_smoke_request.write_request') as write:
                with self.assertRaises(ValueError): published_request(directory,path,'c'*40,b'changed')
                write.assert_not_called()
                published_request(directory,path,'c'*40,canonical(group))
                write.assert_called_once_with(directory,group,'c'*40)
