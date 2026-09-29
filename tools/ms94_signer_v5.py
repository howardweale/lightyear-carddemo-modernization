"""Use the existing host authority in place; never copy a private key into a snapshot."""
from pathlib import Path
from cryptography.hazmat.primitives import serialization
from lightyear_calibration.contracts import read_json, verify, require
from lightyear_calibration.journey_runtime import CONTROL
from lightyear_workflow.campaign_engine import Signer
from lightyear_control_tower.decisions import verify_envelope


class JourneySigner(Signer):
    def __init__(self, root):
        root=Path(root).resolve()
        manifest=read_json(root/'execution-snapshot.json');verify(manifest)
        require(manifest['execution_root']==str(root), 'Signing snapshot identity differs')
        authority=Path(manifest['source_root_for_provenance_only']).resolve()
        require(authority!=root and root.is_relative_to(authority/'work/ms94/execution-snapshots'),
                'Signing authority must remain in the parent development workspace')
        require(not (root/CONTROL/'authority.key.pem').exists(), 'Execution snapshots must not contain a private key')
        self.public=(root/CONTROL/'authority.public.pem').read_bytes()
        require(self.public==(authority/CONTROL/'authority.public.pem').read_bytes(), 'Existing authority public key differs')
        # Load the existing authority for this trusted host process. Do not create,
        # copy, export, transmit or mount it in any execution/compilation container.
        self.key=serialization.load_pem_private_key((authority/CONTROL/'authority.key.pem').read_bytes(),password=None)
        require(verify_envelope(self.sign({'probe':'existing-host-authority'}),self.public),'Authority key pair differs')
