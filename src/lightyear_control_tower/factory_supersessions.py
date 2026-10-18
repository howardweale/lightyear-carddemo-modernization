"""Exact obsolete contract identities; preserved records remain unchanged."""
from .decisions import digest

SUPERSEDED = {'856e8efc25a005c8ba7bbafe9493fde6f7fea0e74915e900632c724cca483c10': 'factory-50bbd415d2da34c3786681ad1ad390d9add581ca17137b2d4f35ecb05fe7a51f', '35ce5a3f754e5b98460544321aaab9919ee70d29b4a81963ee78b997254f492f': 'factory-92c9dab92dfa6db53c1cf72a4784775377a886d81026b67850cbd19f14e806c1'}


def reject_superseded(contract):
    if 'superseded_by' in contract or digest(contract) in SUPERSEDED:
        raise ValueError('factory-request-superseded')
