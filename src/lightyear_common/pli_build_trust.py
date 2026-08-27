from __future__ import annotations

from typing import Any, Mapping

from .asymmetric import rsa_pkcs1v15_sha256_verify


DEVELOPMENT_KEY_ID = "lightyear-pli-development-test-rsa-v1"
DEVELOPMENT_PUBLIC_EXPONENT = 65537
DEVELOPMENT_PUBLIC_MODULUS_HEX = "d4a05f0cfcd481e994a75ad4c6ddec70abdd3d0c23c5e5b1956e333a427e8bac8e1aad0e6a3114002766f6364768a50478cfbb9d8320b4860ca0da378619b07f4e91a0a9684b4e8a8d49b80162a1552f05aac2432b6ff7dbb63052478698e62b94ce0882d50ea3acaee7d7cc40614e4039ef7c4e02148d5c25ccaa838c6b502283babb6312fa315528a914511d8ac4c62be9f19b59bbaf460490795726c77e44994e7ddc8fd1e9b2a7e6cfffd8983cebcf529eb1f86fe431a004cfa637eab01e68891a11a101a255ae78ef1d61e468c13d389ba5dc862766dbb3ea129eb772dd14b7d8cce0bc3f3efcf1df72859f52a82c1ee6963c06374be0a0798886047267"
EXPECTED_WORKFLOW = "howardweale/lightyear-carddemo-modernization/.github/workflows/verify.yml"


def trusted_development_attestation(payload: Mapping[str, Any]) -> bool:
    signature = payload.get("signature", {})
    statement = payload.get("statement", {})
    workflow = (
        statement.get("predicate", {})
        .get("buildDefinition", {})
        .get("externalParameters", {})
        .get("workflow")
    )
    return bool(
        payload.get("schema_version") == "1.0"
        and payload.get("attestation_type") == "lightyear-pli-build-attestation"
        and signature.get("algorithm") == "RSASSA-PKCS1-v1_5-SHA256"
        and signature.get("key_id") == DEVELOPMENT_KEY_ID
        and signature.get("signer_class") == "development-test-key"
        and signature.get("release_authorized") is False
        and workflow == EXPECTED_WORKFLOW
        and rsa_pkcs1v15_sha256_verify(
            statement,
            signature.get("value", ""),
            DEVELOPMENT_PUBLIC_MODULUS_HEX,
            DEVELOPMENT_PUBLIC_EXPONENT,
        )
    )
