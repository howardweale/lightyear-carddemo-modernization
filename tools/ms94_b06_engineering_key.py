"""Separate engineering authority: generate once offline, never use campaign keys."""
import hashlib
import os
from pathlib import Path
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from lightyear_workflow.campaign_engine import Signer

# Replaced only when a newly generated engineering identity is explicitly reviewed.
ENGINEERING_KEY_SHA256 = '4ce00cfa28c13f74c12e6569b6aae010fe7e7185849accad8340c2fc367be9f0'
PRIVATE_NAME = 'engineering.key.pem'
PUBLIC_NAME = 'engineering.public.pem'


def generate_once(directory):
    """Exclusive new directory; private bytes are written once and never read back."""
    directory = Path(directory).absolute()
    if any(p.is_symlink() for p in (directory, *directory.parents)):
        raise ValueError('engineering-key-link')
    directory.mkdir(parents=False, exist_ok=False)
    key = Ed25519PrivateKey.generate()
    public = key.public_key().public_bytes(serialization.Encoding.PEM,
                                          serialization.PublicFormat.SubjectPublicKeyInfo)
    private = key.private_bytes(serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    fd = os.open(directory / PRIVATE_NAME, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(private)
    del private
    with (directory / PUBLIC_NAME).open('xb') as stream:
        stream.write(public)
    return {'public_key_sha256': hashlib.sha256(public).hexdigest(),
            'public_key': str(directory / PUBLIC_NAME), 'private_key': str(directory / PRIVATE_NAME)}


def check_identity(public, expected):
    if expected != ENGINEERING_KEY_SHA256 or hashlib.sha256(public).hexdigest() != expected:
        raise ValueError('engineering-key-fingerprint-mismatch')


class DedicatedEngineeringSigner(Signer):
    def __init__(self, directory, expected):
        directory = Path(directory).absolute()
        if directory.name != 'b06-engineering-authority' or any(
                p.is_symlink() for p in (directory, *directory.parents)):
            raise ValueError('engineering-key-directory')
        self.public = (directory / PUBLIC_NAME).read_bytes()
        check_identity(self.public, expected)  # Refuse before opening any private key.
        self.key = serialization.load_pem_private_key((directory / PRIVATE_NAME).read_bytes(), password=None)
        from lightyear_control_tower.decisions import verify_envelope
        if not verify_envelope(self.sign({'probe': 'engineering-key-pair'}), self.public):
            raise ValueError('engineering-key-pair-mismatch')
