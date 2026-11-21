"""Narrow provider/transport exclusions for controller utility subprocesses.

Not a general allowlist, secure-erasure mechanism or credential-lifetime proof.
"""
import os

def _without_provider_credentials():
    # Check names before value lookup; preserve other environment behavior.
    # The returned copy is passed to utility children, never persisted/logged.
    excluded = {'openai_api_key', 'factory_transport_key'}
    return {name: os.environ[name] for name in os.environ
            if name.casefold() not in excluded}
