"""Host-only adapter for the existing work-order-scoped secret broker."""
from datetime import datetime,timezone

NAMES={'openai':'OPENAI_API_KEY','anthropic':'ANTHROPIC_API_KEY','gemini':'GEMINI_API_KEY'}


class HardenedSecretStore:
    def __init__(self,context):self.context=context

    def read(self,name):
        if name not in NAMES.values():raise ValueError('unsupported provider secret')
        value=self.context.lease_secret('provider',name,datetime.now(timezone.utc).isoformat())
        if not isinstance(value,str) or not value:raise ValueError('provider secret unavailable')
        return value
