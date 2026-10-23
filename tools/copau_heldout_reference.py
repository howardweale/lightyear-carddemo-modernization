"""Offline adapter for the frozen COPAU reference session; operator-private output.

This module never invokes Proof.__init__, seed.main, the twin or a candidate.
Its only supported session body is taken unchanged from the hash-bound judge.
"""
import ast
from copy import deepcopy
import hashlib
import importlib
from itertools import count
import json
from pathlib import Path
import sys

from tools.copau_private_prerequisites import require, encoded, FREEZE_SHA, AMENDMENT_SHA, load_json

PINNED = {
    'factory/carddemo-web/runtime/prove_slice.py': '03d4ecefbcc82a7711ccb7305d028dd29cab4f24cb81c163271cef86cc2b41d1',
    'factory/carddemo-web/runtime/seed.py': '9429b67dfc868cd64dbf2f1ed156e8259ed00561741968dc2b23d68a27c3cccc',
    'src/lightyear_data/carddemo/reference_screens.py': '6936586237129cd2a02ef6e978ca3cead580783f503522380ec9ecc043099793',
    'src/lightyear_data/carddemo/reference_fixture.py': '2be0bcbd8b4b8f10874531d9a17eb9464dca39dd064f0ea86085a7d158104f81',
}


def verify_producer(root):
    freeze_raw = (root / 'docs/factory/copau-factory-judge-freeze-2026-10-18.json').read_bytes()
    amendment_raw = (root / 'docs/factory/copau-factory-judge-freeze-amendment-2026-10-20.json').read_bytes()
    require(hashlib.sha256(freeze_raw).hexdigest() == FREEZE_SHA)
    require(hashlib.sha256(amendment_raw).hexdigest() == AMENDMENT_SHA)
    freeze, amendment = load_json(freeze_raw), load_json(amendment_raw)
    effective = {row['path']: row['sha256'] for row in freeze['files']}
    change = amendment['existing_authorized_change']
    effective[change['path']] = change['sha256']
    effective.update({row['path']: row['sha256'] for row in amendment['files']})
    require(len(effective) == 153)
    for path, digest in effective.items():
        require(hashlib.sha256((root / path).read_bytes()).hexdigest() == digest)
    for path, digest in PINNED.items():
        require(hashlib.sha256((root / path).read_bytes()).hexdigest() == digest)
    require(root.resolve() == Path.cwd().resolve())
    runtime = root / 'factory/carddemo-web/runtime'
    sys.path.insert(0, str(runtime))
    try:
        producer = importlib.import_module('prove_slice')
        fixtures = importlib.import_module('seed')
    finally:
        sys.path.pop(0)
    require(Path(producer.__file__).resolve() == runtime / 'prove_slice.py')
    require(Path(fixtures.__file__).resolve() == runtime / 'seed.py')
    return producer, fixtures


def derive(seed, label, length, alphabet):
    # Domain-separated, deterministic private fixture inputs; no random globals.
    require(isinstance(seed, bytes) and len(seed) == 32)
    raw = hashlib.shake_256(b'copau-heldout-fixture/1\0' + seed + label.encode()).digest(length * 4)
    limit = 256 - 256 % len(alphabet)
    text = ''.join(alphabet[b % len(alphabet)] for b in raw if b < limit)
    require(len(text) >= length)
    return text[:length]


def fixture_inputs(seed, helpers):
    from lightyear_data.carddemo.codec import split_fixed
    root = Path('spec/modernization/carddemo-data')
    plan, entries = helpers.build(root)
    public, records = {}, []
    lookup = {mapping['table']: (layout, mapping) for _, layout, mapping in entries}

    def capture(mapping, raw, ordinal, parent=None):
        records.append(dict(table=mapping['table'], identity=mapping['table'] + ':' + str(ordinal),
                            raw=raw.hex(), segment=mapping.get('segment', {}).get('name'), parent=parent,
                            keys=[dict(length=k['key_length'], offset=k['key_offset'],
                                       value=raw[k['key_offset']:k['key_offset'] + k['key_length']].hex())
                                  for k in mapping['keys']]))

    for item, layout, mapping in entries:
        if not item.get('synthetic'):
            rows = list(split_fixed((root / 'upstream' / item['data']).read_bytes(), layout.record_length))
            public[mapping['table']] = rows
            for ordinal, raw in enumerate(rows, 1):
                capture(mapping, raw, ordinal)
    xl, xm = lookup['cardxref']
    xref = public['cardxref'][0]
    account = str(helpers.value(xl, xm, xref, 'XREF-ACCT-ID')).zfill(11)
    customer = str(helpers.value(xl, xm, xref, 'XREF-CUST-ID')).zfill(9)
    card = str(helpers.value(xl, xm, xref, 'XREF-CARD-NUM'))
    ul, um = lookup['usrsec']
    user = next(row for row in public['usrsec'] if helpers.value(ul, um, row, 'SEC-USR-TYPE') == 'U')
    login = dict(account=account, user=helpers.value(ul, um, user, 'SEC-USR-ID').strip(),
                 password=helpers.value(ul, um, user, 'SEC-USR-PWD').strip())
    sl, sm = lookup['pautsum0']; dl, dm = lookup['pautdtl1']
    capture(sm, helpers.fixture(sl, sm, {'PA-ACCT-ID': account, 'PA-CUST-ID': customer,
                                        'PA-APPROVED-AUTH-CNT': 7, 'PA-APPROVED-AUTH-AMT': '86.38'}), 1)
    private_inputs = []
    for ordinal in range(1, 8):
        prefix = str(ordinal) + ':'
        # Merchant display identifiers are valid scenario business fields, not
        # appended canaries. The reference must actually return their bytes.
        merchant = derive(seed, prefix + 'merchant', 22, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ')
        fields = {'PA-AUTH-DATE-9C': 99999 - 26000 - ordinal,
                  'PA-AUTH-TIME-9C': 999999999 - 123456000 - ordinal,
                  'PA-AUTH-ORIG-DATE': '261017', 'PA-AUTH-ORIG-TIME': '123456',
                  'PA-CARD-NUM': card, 'PA-AUTH-TYPE': 'AUTH', 'PA-CARD-EXPIRY-DATE': '2912',
                  'PA-AUTH-RESP-CODE': '00', 'PA-AUTH-RESP-REASON': '0000',
                  'PA-TRANSACTION-AMT': '12.34', 'PA-APPROVED-AMT': '12.34',
                  'PA-MERCHANT-CATAGORY-CODE': '1234', 'PA-ACQR-COUNTRY-CODE': '840',
                  'PA-MERCHANT-ID': derive(seed, prefix + 'merchant-id', 10, '0123456789'),
                  'PA-MERCHANT-NAME': merchant,
                  'PA-MERCHANT-CITY': derive(seed, prefix + 'city', 13, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'),
                  'PA-MERCHANT-STATE': 'WA', 'PA-MERCHANT-ZIP': '981010000',
                  'PA-TRANSACTION-ID': derive(seed, prefix + 'transaction', 15, '0123456789'),
                  'PA-MATCH-STATUS': 'P', 'PA-AUTH-FRAUD': ' '}
        raw = helpers.fixture(dl, dm, fields)
        require(helpers.value(dl, dm, raw, 'PA-MERCHANT-NAME').rstrip() == merchant)
        capture(dm, raw, ordinal, 'pautsum0:1')
        private_inputs.append(fields)
    return login, dict(schema='carddemo-raw-proof-fixture/1', records=records, plan=plan), private_inputs


def run_session(root, seed):
    producer, fixtures = verify_producer(root)
    login, raw, inputs = fixture_inputs(seed, fixtures)

    class Offline:
        start = producer.Proof.start
        inputs = producer.Proof.inputs

        def __init__(self):
            self.fixture = login
            self.engine = producer.Engine(raw)
            self.engine.store.fraud = []
            self.sessions = count(1)
            self.rows = []
            self.current = None

        def step(self, aid, fields=None):
            result = self.engine.step(aid, fields or {})
            self.current = result['screen']
            self.rows.append(deepcopy(dict(aid=aid, fields=fields or {}, result=result,
                                          fraud=self.engine.store.fraud)))
            return result

    driver = Offline()
    tree = ast.parse((root / 'factory/carddemo-web/runtime/prove_slice.py').read_bytes())
    proof = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'Proof')
    run = next(n for n in proof.body if isinstance(n, ast.FunctionDef) and n.name == 'run')
    matches = [n for n in run.body if isinstance(n, ast.FunctionDef) and n.name == 'authorizations']
    require(len(matches) == 1)
    # Execute the original pinned nested session body with its original assertions.
    # No rewritten scenario, Proof constructor, HTTP request or snapshot call.
    namespace = dict(self=driver, deepcopy=deepcopy)
    exec(compile(ast.Module(body=matches, type_ignores=[]), '<pinned-copau-session>', 'exec'), namespace)
    namespace['authorizations']()
    programs = {row['result']['program'] for row in driver.rows}
    require({'COPAUS0C', 'COPAUS1C'} <= programs)
    require(any(row['fraud'] and row['fraud'][-1]['auth_fraud'] == 'F' for row in driver.rows))
    require(any(row['fraud'] and row['fraud'][-1]['auth_fraud'] == 'R' for row in driver.rows))
    values, bindings = [], []
    for fields in inputs:
        # 20 real returned EBCDIC merchant bytes, encoded exactly as the judge's
        # returned COMMAREA. 26**20 choices (~94 bits) under a private random seed.
        value = fields['PA-MERCHANT-NAME'][:20].encode('cp037').hex()
        require(len(value) == 40 and len(set(fields['PA-MERCHANT-NAME'][:20])) >= 10)
        found = [(i, row['result']['commarea'].find(value)) for i, row in enumerate(driver.rows)
                 if row['result']['program'] in {'COPAUS0C', 'COPAUS1C'}
                 and value in row['result']['commarea']]
        if found:
            require(value not in values)
            values.append(value)
            bindings.append(dict(record=len(values), interaction=found[0][0],
                                 output='commarea', character_offset=found[0][1], length=40))
    require(1 <= len(values) <= 7)
    private = dict(producer=PINNED, session='Proof.run.authorizations', input_fields=inputs,
                   fixture_sha256=hashlib.sha256(encoded(raw)).hexdigest(),
                   output_sha256=hashlib.sha256(encoded(producer.canonical(driver.rows))).hexdigest(),
                   interactions=len(driver.rows), selected_output_bindings=bindings)
    return values, private
