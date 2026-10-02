"""Identity boundary; local credentials today, replaceable provider for future SSO."""

import hashlib
import hmac
from typing import Protocol
from .decisions import DecisionUnauthorized


class IdentityProvider(Protocol):
    authentication: str

    def authenticate(self, credential: str, operators: list[dict]) -> dict: ...


class LocalIdentityProvider:
    authentication = "individual-local-credential"

    def authenticate(self, credential, operators):
        if not isinstance(credential, str) or not 1 <= len(credential) <= 300:
            raise DecisionUnauthorized("Invalid credential")
        supplied = hashlib.sha256(credential.encode()).hexdigest()
        for operator in operators:
            if hmac.compare_digest(supplied, operator["token_sha256"]):
                return operator
        raise DecisionUnauthorized("Invalid credential")
