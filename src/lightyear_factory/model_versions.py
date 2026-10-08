"""Prospective graph evaluations require a dated, response-verified snapshot."""
import re
from datetime import date

def require_snapshot(value):
    if not isinstance(value,str):raise ValueError('dated model snapshot required')
    match=re.search(r'(?:^|[-_])(20[0-9]{2})-?([01][0-9])-?([0-3][0-9])$',value)
    if not match:raise ValueError('dated model snapshot required; aliases are not admitted')
    date(*map(int,match.groups()))
    return value

def verify_response(provider,response):
    if getattr(provider,'require_snapshot_response',False):
        require_snapshot(provider.model)
        actual=response.get('modelVersion') if provider.provider_id=='gemini-generate-content' else response.get('model')
        if actual!=provider.model:raise ValueError('response model snapshot differs or absent')
