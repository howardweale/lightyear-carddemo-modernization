"""Read only pinned public signatures; never mount the upstream tree for a model."""
import re
from lightyear_calibration.contracts import read_json, verify, seal, require
from lightyear_calibration.journey_order import save
from tools.ms94_v3_development import API_FILES, SOURCE_COMMIT

CATALOG = 'factory/idempiere/stage-b-v4/public-api.json'


def prepare(root):
    from tools.ms94_v3_development import api as source_api
    entries = {name: source_api(root, name) for name in sorted(API_FILES)}
    value = seal({'source_commit': SOURCE_COMMIT, 'classes': entries,
                  'public_signatures_only': True, 'private_business_outputs': False})
    save(root/CATALOG, value)
    return value


def api(root, name, method=''):
    require(name in API_FILES, 'Class is outside the public API allowlist')
    require(not method or re.fullmatch(r'[A-Za-z_$][A-Za-z0-9_$]*', method), 'Invalid method selector')
    catalog = read_json(root/CATALOG); verify(catalog)
    require(catalog['source_commit'] == SOURCE_COMMIT, 'API source commit changed')
    entry = catalog['classes'][name]; verify(entry)
    value = {k:v for k,v in entry.items() if k != 'content_sha256'}
    if method:
        def selected(values):
            return [s for s in values if re.search(r'\b'+re.escape(method)+r'\s*\(', s)]
        value['signatures'] = selected(entry['signatures'])
        value['inherited_generated_api'] = [
            {**parent, 'signatures': selected(parent['signatures'])}
            for parent in entry['inherited_generated_api']]
    return seal(value)
