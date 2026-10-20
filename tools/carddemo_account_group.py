"""Compose bound four-group account proof inputs; rendering/publication and approval are separate."""
from hashlib import sha256
from tools.carddemo_account_archive import verify_archives, verify_receipt_hashes
from tools.carddemo_account_evidence import BoundEvidence, json_document, json_rows, reference
from tools.carddemo_account_git import verify_git_sources
from tools.carddemo_account_identity import verify_receipt_identity
from tools.carddemo_account_mutation import BASELINE, verify_mutation_gate
from tools.carddemo_account_proof import GROUPS
from tools.carddemo_account_scenarios import verify_scenarios
from tools.carddemo_account_scope import project_scope
from tools.carddemo_account_observations import verify_observations

SCOPES = {
    'account_input_java': 'spec/modernization/carddemo-screens/idiomatic-account-input-scope.json',
    'account_text_money_java': 'spec/modernization/carddemo-screens/idiomatic-account-text-money-scope.json',
    'account_ssn_fico_java': 'spec/modernization/carddemo-screens/idiomatic-account-ssn-fico-scope.json',
    'account_location_java': 'spec/modernization/carddemo-screens/idiomatic-account-location-scope.json',
}
COBOL = 'spec/modernization/carddemo-screens/upstream/app/cbl/COACTUPC.cbl'
PROOF_SOURCES = {'factory/carddemo-web/runtime/snapshot.py', '.github/workflows/carddemo-web.yml',
    'factory/carddemo-web/service/src/test/java/ai/lightyear/carddemo/AccountLocationRulesTest.java'}
REPOSITORY = 'https://github.com/howardweale/lightyear-carddemo-modernization'


def _required_source_paths(receipt):
    hashes = receipt.get('hashes')
    if not isinstance(hashes, dict):
        raise ValueError('account-loader-source-inventory')
    paths = set()
    for rows in hashes.values():
        if not isinstance(rows, list): raise ValueError('account-loader-source-inventory')
        for row in rows:
            path, _ = reference(row)
            if not path.startswith('work/'): paths.add(path)
    return paths


def _input_closure(desc, evidence, descriptor_path):
    """Every captured file has exactly one descriptor role; descriptor stays outside manifest."""
    if not isinstance(desc['archives'], dict) or not isinstance(desc['source_bindings'], dict):
        raise ValueError('account-loader-input-bindings')
    refs = [desc['inventory'], desc['run'], *desc['archives'].values(),
            *desc['source_bindings'].values(), *desc.get('git_objects', {}).values()]
    manifest_path, _ = reference(desc['manifest'])
    seen = {descriptor_path.casefold(), manifest_path.casefold()}
    if len(seen) != 2: raise ValueError('account-loader-input-alias')
    paths = set()
    for value in refs:
        path, _ = reference(value)
        if path.casefold() in seen: raise ValueError('account-loader-input-alias')
        seen.add(path.casefold()); paths.add(path)
        evidence.read(value)
    if set(evidence.inputs) != paths | {manifest_path}:
        raise ValueError('account-loader-input-closure')


def load_account_group(root, git_root, descriptor_ref):
    """Descriptor digest is caller-reviewed; all referenced data are captured before semantic checks."""
    # Bootstrap descriptor through the same strict byte/path reader used for other inputs.
    from tools.carddemo_account_evidence import _read
    from pathlib import Path
    descriptor_path, digest = reference(descriptor_ref)
    raw = _read(Path(root).resolve(strict=True), descriptor_path)
    if sha256(raw).hexdigest() != digest: raise ValueError('account-loader-descriptor-hash')
    desc = json_document(raw)
    keys = {'schema', 'program', 'whole_screen_idiomatic', 'publication_date', 'source_head',
            'tested_commit', 'base_head', 'manifest', 'inventory', 'run', 'archives',
            'receipt_member', 'source_bindings', 'git_objects'}
    if set(desc) != keys or desc['schema'] != 'carddemo-account-publication-inputs/1':
        raise ValueError('account-loader-descriptor')
    evidence = BoundEvidence(root, desc['manifest'])
    _input_closure(desc, evidence, descriptor_path)
    inventory = evidence.document(desc['inventory']); run = evidence.document(desc['run'])
    archives = verify_archives(evidence, inventory, desc['archives'])
    member_path, member_digest = reference(desc['receipt_member'])
    if member_path not in archives['carddemo-unsigned-receipt']:
        raise ValueError('account-loader-receipt-member')
    receipt_raw = archives['carddemo-unsigned-receipt'][member_path]
    if sha256(receipt_raw).hexdigest() != member_digest:
        raise ValueError('account-loader-receipt-hash')
    receipt = json_document(receipt_raw)
    identity = verify_receipt_identity(receipt, run, desc['source_head'], desc['tested_commit'])
    if member_path != 'carddemo-slice-1-' + identity['original_receipt_date'] + '.json':
        raise ValueError('account-loader-receipt-date')
    source_paths = _required_source_paths(receipt)
    bindings = desc['source_bindings']
    required = source_paths | set(SCOPES.values()) | {BASELINE} | PROOF_SOURCES
    if not isinstance(bindings, dict) or set(bindings) != required or COBOL not in source_paths:
        raise ValueError('account-loader-source-closure')
    sources = verify_git_sources(desc['git_objects'], evidence, desc['source_head'], desc['tested_commit'],
                                 desc['base_head'], bindings)
    if (type(inventory.get('run')) is not int or inventory['run'] != identity['run_id']
            or inventory.get('source_head') != identity['source_head']
            or inventory.get('tested_commit') != identity['tested_commit']
            or inventory.get('tested_tree') != sources['tree']
            or inventory.get('run_url') != REPOSITORY + '/actions/runs/' + str(identity['run_id'])):
        raise ValueError('account-loader-inventory-identity')
    closure = verify_receipt_hashes(receipt, archives, evidence, {path: bindings[path] for path in source_paths})
    mutation = verify_mutation_gate(archives['carddemo-proof-mutation']['pit-reports/mutations.xml'],
                                    evidence.read(bindings[BASELINE]), receipt['gates']['mutation'])
    references = {}
    for mode in ('api', 'browser', 'mutation'):
        files = archives['carddemo-proof-' + mode]
        references[mode + '-reference'] = {'summary': json_document(files['reference/summary.json']),
                                           'rows': json_rows(files['reference/cases.json'])}
    scenarios = verify_scenarios(receipt['gates'], references,
        json_document(archives['carddemo-proof-browser']['browser/summary.json']), desc['tested_commit'])
    scopes = {group: evidence.document(bindings[path]) for group, path in SCOPES.items()}
    cobol_source = {'path': COBOL, 'sha256': sources['sources'][COBOL]['sha256']}
    scope = project_scope(desc, scopes, cobol_source, identity['measurement_date'])
    for group, value in scope['groups'].items():
        if not {'factory/carddemo-web/service/src/main/java/ai/lightyear/carddemo/' + name
                for name in value['java_files']}.issubset(source_paths):
            raise ValueError('account-loader-java-source-closure')
        for name in GROUPS[group]:
            path = 'factory/carddemo-web/service/src/main/java/ai/lightyear/carddemo/' + name + '.java'
            if path not in source_paths: raise ValueError('account-loader-class-source')
    return {'schema': 'carddemo-account-bound-proof/1', 'identity': identity, 'scope': scope,
            'hash_closure': closure, 'mutation': mutation, 'scenarios': scenarios, 'git_sources': sources,
            'observations': verify_observations(archives, scopes, cobol_source),
            'receipt': receipt, 'descriptor': descriptor_ref,
            'inputs': [descriptor_path, *evidence.inputs],
            'scope_binding': 'separate exact-source Git blobs; not claimed as original receipt inputs',
            'whole_screen_idiomatic': False, 'activation_authorized': False, 'phase2_authorized': False}
