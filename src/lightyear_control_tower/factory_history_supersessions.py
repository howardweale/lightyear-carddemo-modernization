"""Historical backfill contracts already superseded by the recorded activation."""
from hashlib import sha256
from .decisions import canonical

SUPERSEDED = {'fb2c60065fbb9792bfe7765409fcb3e9097cd1a61fd46f785832088873f18e0e': 'docs/factory/factory-local-activation-correction-2026-10-17.json', '23ffd5264ce930ebdc916a877b988158fcefb6432e23dac0cb740b0433353472': 'docs/factory/factory-local-activation-correction-2026-10-17.json'}

def reject_historical_supersession(contract):
    if contract.get('superseded_by') or sha256(canonical(contract)).hexdigest() in SUPERSEDED:
        raise ValueError('factory-backfill-request-superseded')
