"""Howard-only offline preparation. Never signs, launches, or contacts Tower.

The CLI has one private root and fixed private filenames. CI uses disposable
synthetic stores through the API; the CLI refuses non-Windows hosts.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import stat
import subprocess
import sys
import uuid

ROOT = Path('C:/ProgramData/Lightyear/FactoryControllerPrivate-v1')
LIMIT = 262144
ID = re.compile(r'[A-Za-z][A-Za-z0-9_.:-]{0,127}')
SHA = re.compile(r'[0-9a-f]{64}')
REF = re.compile(r'copau-prerequisites-[0-9a-f]{32}')
FREEZE_SHA = 'f7f68623af3773c0a71f0d3dc82da4932a5d61993feb01595957179c9cff49ee'
AMENDMENT_SHA = 'd226935e37a19b611cff5d05f383d7d37f1835449b36c600abfe913cee3bfe22'


def windows_host():
    return os.name == 'nt'


class Refused(Exception):
    """No underlying exception text, paths or private values cross the CLI."""


def require(condition):
    if not condition:
        raise Refused()


def load_json(raw):
    def pairs(rows):
        result = {}
        for key, value in rows:
            require(key not in result)
            result[key] = value
        return result
    return json.loads(raw.decode('utf-8'), object_pairs_hook=pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(Refused()))


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True,
                       separators=(',', ':'), allow_nan=False) + '\n').encode('utf-8')


def bundle_info(raw):
    require(1 <= len(raw) <= LIMIT)
    data = load_json(raw)
    require(isinstance(data, dict) and set(data) == {'schema', 'values'}
            and data['schema'] == 'factory-private-expected-values/1')
    values = data['values']
    require(isinstance(values, list) and 1 <= len(values) <= 64)
    require(all(isinstance(v, str) and len(''.join(v.casefold().split())) >= 40
                for v in values))
    require(len(set(values)) == len(values))
    # Also refuse canonical duplicates; stricter than the runtime's exact check.
    require(len({''.join(v.casefold().split()) for v in values}) == len(values))
    return dict(sha256=hashlib.sha256(raw).hexdigest(), size_bytes=len(raw), count=len(values))


def no_links(path):
    require(path.is_absolute() and '..' not in path.parts)
    for item in (path, *path.parents):
        info = item.lstat()
        require(not stat.S_ISLNK(info.st_mode)
                and not getattr(info, 'st_file_attributes', 0) & 0x400)
    require(path.resolve(strict=True) == path)


def identity(info):
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns


# Only public filesystem metadata travels to PowerShell. No secret is passed
# in argv, environment, stdout, stderr or a temporary script.
ACL_SCRIPT = r'''
$ErrorActionPreference='Stop'
$p=[Console]::In.ReadToEnd() | ConvertFrom-Json
$sid=[Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$rows=@(foreach($path in $p) {
  $a=if ([IO.Directory]::Exists($path)) {
    [IO.Directory]::GetAccessControl($path)
  } else {
    [IO.File]::GetAccessControl($path)
  }
  $rules=@($a.GetAccessRules($true,$true,[Security.Principal.SecurityIdentifier]) | ForEach-Object {
    @{sid=$_.IdentityReference.Value;rights=[long]$_.FileSystemRights;
      allow=($_.AccessControlType -eq 'Allow');inheritOnly=([int]$_.PropagationFlags -band 2) -ne 0}
  })
  @{owner=$a.GetOwner([Security.Principal.SecurityIdentifier]).Value;
    protected=$a.AreAccessRulesProtected;rules=$rules}
})
@{sid=$sid;rows=$rows} | ConvertTo-Json -Depth 6 -Compress
'''


def powershell(script, value):
    executable = Path(os.environ['SystemRoot']) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
    result = subprocess.run([str(executable), '-NoProfile', '-NonInteractive', '-Command', script],
                            input=encoded(value), stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, timeout=30, check=False)
    require(result.returncode == 0)
    return result.stdout


def windows_acl(paths):
    response = load_json(powershell(ACL_SCRIPT, [str(p) for p in paths]))
    require(response['sid'] not in {'S-1-5-18', 'S-1-5-19', 'S-1-5-20'})
    require(len(response['rows']) == len(paths))
    return response['sid'], response['rows']


def private_acl(row, sid, directory=False):
    require(row['owner'] in ({sid} if directory else {sid, 'S-1-5-32-544'})
            and (not directory or row['protected']))
    allowed = [r for r in row['rules'] if r['allow']]
    require(allowed and all(r['sid'] == sid for r in allowed))
    require(any(not r['inheritOnly'] and r['rights'] & 0x1F01FF == 0x1F01FF for r in allowed))


def ancestors_acl(rows, sid):
    trusted = {sid, 'S-1-5-18', 'S-1-5-32-544',
               'S-1-5-80-956008885-3418522649-1831038044-1853292631-2271478464'}
    # Parent delete-child permits replacing a protected child. Delete, WRITE_DAC
    # and WRITE_OWNER permit replacing or changing an ancestor itself.
    dangerous = 0x40 | 0x10000 | 0x40000 | 0x80000
    for row in rows:
        require(row['owner'] in trusted)
        require(not any(r['allow'] and not r['inheritOnly'] and r['sid'] not in trusted
                        and r['rights'] & dangerous for r in row['rules']))


def check_acl(root, file=None):
    paths = [root] + ([file] if file else []) + list(root.parents)
    if os.name == 'nt':
        sid, rows = windows_acl(paths)
        private_acl(rows[0], sid, True)
        if file:
            private_acl(rows[1], sid)
        ancestors_acl(rows[2 if file else 1:], sid)
    else:
        # CI synthetic filesystem checks. The CLI never uses this backend.
        for path in [root] + ([file] if file else []):
            info = path.stat()
            require(info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) & 0o077 == 0)


INIT_SCRIPT = r'''
$ErrorActionPreference='Stop'
$path=[Console]::In.ReadToEnd() | ConvertFrom-Json
if (Test-Path -LiteralPath $path) {throw 'refused'}
$sid=[Security.Principal.WindowsIdentity]::GetCurrent().User
$acl=New-Object Security.AccessControl.DirectorySecurity
$acl.SetAccessRuleProtection($true,$false)
$acl.SetOwner($sid)
$acl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new(
  $sid,'FullControl','ContainerInherit,ObjectInherit','None','Allow'))
# Windows PowerShell 5.1 / .NET Framework creates the directory with its DACL;
# no secret or permissive intermediate directory is created.
[IO.Directory]::CreateDirectory($path,$acl) | Out-Null
'''


class Store:
    def __init__(self, root, exposed_roots):
        self.root = Path(root)
        require(self.root.is_absolute() and '..' not in self.root.parts)
        require(exposed_roots)
        self.exposed = tuple(Path(p).resolve(strict=True) for p in exposed_roots)

    def location(self):
        # Refuse overlaps in either direction, including checkout/workspace/run
        # roots explicitly supplied by the operator. Never enumerate their data.
        for other in self.exposed:
            require(self.root != other and other not in self.root.parents
                    and self.root not in other.parents)
        require(not any((p / '.git').exists() for p in (self.root, *self.root.parents)))

    def initialize(self):
        self.location()
        require(not os.path.lexists(self.root))
        no_links(self.root.parent)
        if os.name == 'nt':
            sid, rows = windows_acl(list(self.root.parents))
            ancestors_acl(rows, sid)
            powershell(INIT_SCRIPT, str(self.root))
        else:
            self.root.mkdir(mode=0o700)
        self.check()

    def check(self):
        self.location()
        no_links(self.root)
        require(self.root.is_dir())
        check_acl(self.root)

    def path(self, name):
        require(re.fullmatch('[a-z][a-z0-9-]*[.]json|work-order-hmac[.]txt', name))
        return self.root / name

    def read(self, name, limit=LIMIT):
        self.check()
        path = self.path(name)
        no_links(path)
        check_acl(self.root, path)
        before = path.stat()
        require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and 0 < before.st_size <= limit)
        with path.open('rb') as stream:
            require(identity(os.fstat(stream.fileno())) == identity(before))
            raw = stream.read(limit + 1)
            require(identity(os.fstat(stream.fileno())) == identity(before))
        no_links(path)
        require(identity(path.stat()) == identity(before) and len(raw) == before.st_size)
        check_acl(self.root, path)
        return raw

    def absent(self, *names):
        self.check()
        require(all(not os.path.lexists(self.path(name)) for name in names))

    def write(self, name, raw):
        self.absent(name)
        require(0 < len(raw) <= LIMIT)
        path = self.path(name)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        require(self.read(name) == raw)


def key_info(store, issuer, key_id, create=False):
    require(isinstance(issuer, str) and ID.fullmatch(issuer)
            and isinstance(key_id, str) and ID.fullmatch(key_id)
            and key_id not in {'schema-validation-only', 'lightyear-release-operator'})
    store.absent('work-order-custody.json')
    if create:
        store.absent('work-order-hmac.txt')
        store.write('work-order-hmac.txt', secrets.token_hex(32).encode('ascii'))
    raw = store.read('work-order-hmac.txt', 4096)
    text = raw.decode('utf-8')
    require(32 <= len(raw) <= 4096 and text == text.strip() and '\x00' not in text)
    record = dict(issuer=issuer, key_id=key_id, algorithm='HMAC-SHA256',
                  custody='operator-controller-only', recovery_copy='operator-responsibility',
                  created_by_helper=create)
    store.write('work-order-custody.json', encoded(dict(record, key_sha256=hashlib.sha256(raw).hexdigest())))
    return record


def prepare_bundle(store, freeze_sha, amendment_sha, existing=False):
    require(freeze_sha == FREEZE_SHA and amendment_sha == AMENDMENT_SHA)
    store.absent('bundle-binding.json')
    if not existing:
        store.absent('copau-expected-values.json')
    # The private provenance is retained privately. This is an operator
    # attestation, not an automated claim that values are a qualified oracle.
    provenance = load_json(store.read('expected-source.json'))
    require(isinstance(provenance, dict) and set(provenance) == {
        'schema', 'freeze_sha256', 'amendment_sha256', 'source_reference',
        'coverage_description', 'approved_expected_state_source', 'values'})
    require(provenance['schema'] == 'copau-private-source/1'
            and provenance['freeze_sha256'] == freeze_sha
            and provenance['amendment_sha256'] == amendment_sha
            and provenance['approved_expected_state_source'] is True)
    require(all(isinstance(provenance[k], str) and 1 <= len(provenance[k]) <= 8192
                for k in ('source_reference', 'coverage_description')))
    prepared = encoded(dict(schema='factory-private-expected-values/1', values=provenance['values']))
    bundle_info(prepared)
    if existing:
        raw = store.read('copau-expected-values.json')
        info = bundle_info(raw)
        require(load_json(raw) == load_json(prepared))
    else:
        raw = prepared
        info = bundle_info(raw)
        store.write('copau-expected-values.json', raw)
    store.write('bundle-binding.json', encoded(info))
    return info


def public_record(store, reviewed_commit, freeze_sha, amendment_sha):
    require(re.fullmatch('[0-9a-f]{40}', reviewed_commit)
            and freeze_sha == FREEZE_SHA and amendment_sha == AMENDMENT_SHA)
    store.absent('public-prerequisites.json')
    custody = load_json(store.read('work-order-custody.json', 8192))
    require(set(custody) == {'issuer', 'key_id', 'algorithm', 'custody', 'recovery_copy', 'created_by_helper', 'key_sha256'})
    require(ID.fullmatch(custody['issuer']) and ID.fullmatch(custody['key_id'])
            and custody['algorithm'] == 'HMAC-SHA256'
            and custody['custody'] == 'operator-controller-only'
            and custody['recovery_copy'] == 'operator-responsibility'
            and type(custody['created_by_helper']) is bool)
    key = store.read('work-order-hmac.txt', 4096)
    require(32 <= len(key) <= 4096 and key.decode('utf-8') == key.decode('utf-8').strip()
            and b'\0' not in key)
    require(hashlib.sha256(key).hexdigest() == custody.pop('key_sha256'))
    info = bundle_info(store.read('copau-expected-values.json'))
    require(info == load_json(store.read('bundle-binding.json', 8192)))
    source = load_json(store.read('expected-source.json'))
    require(source['freeze_sha256'] == freeze_sha and source['amendment_sha256'] == amendment_sha
            and source['approved_expected_state_source'] is True
            and source['values'] == load_json(store.read('copau-expected-values.json'))['values'])
    record = dict(schema='copau-public-prerequisites/1',
                  attestation_reference='copau-prerequisites-' + uuid.uuid4().hex,
                  prepared_at=datetime.now(timezone.utc).isoformat(),
                  reviewed_helper_commit=reviewed_commit,
                  helper_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  freeze_sha256=freeze_sha, amendment_sha256=amendment_sha,
                  work_order=custody, private_expected_values=info,
                  source_coverage='operator-attested-not-independently-verified',
                  signed=False, run_authorized=False)
    validate_public(record)
    store.write('public-prerequisites.json', encoded(record))
    return record


def validate_public(record):
    require(isinstance(record, dict) and set(record) == {
        'schema', 'attestation_reference', 'prepared_at', 'reviewed_helper_commit',
        'helper_sha256', 'freeze_sha256', 'amendment_sha256', 'work_order',
        'private_expected_values', 'source_coverage', 'signed', 'run_authorized'})
    require(record['schema'] == 'copau-public-prerequisites/1'
            and REF.fullmatch(record['attestation_reference'])
            and re.fullmatch('[0-9a-f]{40}', record['reviewed_helper_commit'])
            and datetime.fromisoformat(record['prepared_at']).utcoffset() is not None
            and SHA.fullmatch(record['helper_sha256'])
            and record['freeze_sha256'] == FREEZE_SHA and record['amendment_sha256'] == AMENDMENT_SHA
            and record['signed'] is False and record['run_authorized'] is False
            and record['source_coverage'] == 'operator-attested-not-independently-verified')
    key = record['work_order']
    require(set(key) == {'issuer', 'key_id', 'algorithm', 'custody', 'recovery_copy', 'created_by_helper'}
            and ID.fullmatch(key['issuer']) and ID.fullmatch(key['key_id'])
            and key['key_id'] not in {'schema-validation-only', 'lightyear-release-operator'}
            and key['algorithm'] == 'HMAC-SHA256' and key['custody'] == 'operator-controller-only'
            and key['recovery_copy'] == 'operator-responsibility' and type(key['created_by_helper']) is bool)
    info = record['private_expected_values']
    require(set(info) == {'sha256', 'size_bytes', 'count'} and SHA.fullmatch(info['sha256'])
            and type(info['size_bytes']) is int and 1 <= info['size_bytes'] <= LIMIT
            and type(info['count']) is int and 1 <= info['count'] <= 64)
    return record


def main():
    try:
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument('action', choices=['initialize', 'create-key', 'register-key',
                                              'prepare-bundle', 'register-bundle', 'public-metadata'])
        parser.add_argument('--exposed-root', action='append', required=True)
        parser.add_argument('--issuer')
        parser.add_argument('--key-id')
        parser.add_argument('--freeze-sha256', default=FREEZE_SHA)
        parser.add_argument('--amendment-sha256', default=AMENDMENT_SHA)
        parser.add_argument('--reviewed-commit')
        args = parser.parse_args()
        require(windows_host())
        # Always exclude the checkout/script tree and current working directory,
        # in addition to the complete operator-supplied exposure inventory.
        store = Store(ROOT, [Path(__file__).resolve().parents[1], Path.cwd(), *args.exposed_root])
        if args.action == 'initialize':
            store.initialize()
        elif args.action in {'create-key', 'register-key'}:
            if args.action == 'create-key':
                require(input('Type CREATE NEW COPAU KEY only if no suitable key exists: ') == 'CREATE NEW COPAU KEY')
            key_info(store, args.issuer, args.key_id, args.action == 'create-key')
        elif args.action in {'prepare-bundle', 'register-bundle'}:
            require(input('Type APPROVED PRIVATE EXPECTED STATE to attest the source and coverage: ')
                    == 'APPROVED PRIVATE EXPECTED STATE')
            prepare_bundle(store, args.freeze_sha256, args.amendment_sha256, args.action == 'register-bundle')
        else:
            public_record(store, args.reviewed_commit, args.freeze_sha256, args.amendment_sha256)
        print('PREPARED: private files preserved; no signature or run requested.')
        return 0
    except Exception:
        print('REFUSED: preserve existing files; inspect privately. No automatic retry.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
