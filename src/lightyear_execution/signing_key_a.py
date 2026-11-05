"""Public identities returned by Howard; no hardware or signing authority.

PEM file hashes were independently reproduced from the human's public photo.
Source/work-order scope must still be supplied explicitly for each designation.
"""
from .external_signing import SigningRefused, _pem
from .signing_designation import prepare_designation

DESIGNATION_ID = "howard-darkfactory-key-a"
PUBLIC_KEYS = {
    "controller-receipt": (
        b"-----BEGIN PUBLIC KEY-----\n"
        b"MCowBQYDK2VwAyEA2GUU3oXWxz6tVr8NwFDM/y21cW3U7qT4S5bw/c0JjlE=\n"
        b"-----END PUBLIC KEY-----\n",
        "58c97a1c25b649a8d61b4b36afe5ae8099d953720892f97764021a343e533c8c",
    ),
    "candidate-commit": (
        b"-----BEGIN PUBLIC KEY-----\n"
        b"MCowBQYDK2VwAyEAhzRF07oOh0DZgq3HOcEW2TugFdfv7YrJPQl7GSGpg7A=\n"
        b"-----END PUBLIC KEY-----\n",
        "a0627e8ffe1c74f610b92175b0486e37ef0552b503976fba5a983f268eaa677a",
    ),
}


def prepare_key_a_designation(*, source_commit, work_order_sha256):
    """Produce unsigned scoped bytes, never fill in an unapproved final E."""
    for pem, digest in PUBLIC_KEYS.values():
        _pem(pem, digest)
    return prepare_designation(
        PUBLIC_KEYS["controller-receipt"][0], PUBLIC_KEYS["candidate-commit"][0],
        designation_id=DESIGNATION_ID, source_commit=source_commit,
        work_order_sha256=work_order_sha256, host_label="DarkFactory",
        custodian="Howard", revocation_contact="Howard")


def require_key_a_designation(prepared, binding):
    expected = prepare_key_a_designation(
        source_commit=binding.source_commit, work_order_sha256=binding.work_order_sha256)
    if prepared != expected:
        raise SigningRefused("registered-key-a-designation-required")
