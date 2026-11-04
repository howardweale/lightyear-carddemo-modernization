"""Bounded decoding of original outcome ZIP bytes; no artifact provenance grant.

Expected ZIP digest and outcome bindings must be independently reviewed, not
read from this archive. Native envelope checks do not establish controller
origin, strict predicates, signer designation or authenticated CI provenance.
No extraction, signing, downloading, qualification or authority receipt.
"""
from hashlib import sha256
from io import BytesIO
import re,stat,zipfile
from tools.ci.configured_outcome_inventory import _limits,_require,check_outcome_inventory_bytes
MAX_ARCHIVE=32*1024*1024

def decode_outcome_archive(raw,expected_sha256):
    # Pure untrusted-byte decoding. A matching digest alone is not provenance.
    _require(type(raw) is bytes and 0<len(raw)<=MAX_ARCHIVE,'archive-size')
    _require(type(expected_sha256) is str and re.fullmatch('[0-9a-f]{64}',expected_sha256)
        and sha256(raw).hexdigest()==expected_sha256,'archive-digest')
    limits=_limits()
    with zipfile.ZipFile(BytesIO(raw)) as archive:
        entries=archive.infolist()
        _require(len(entries)==len(limits) and {row.filename for row in entries}==set(limits),
            'archive-exact-inventory')
        _require(sum(row.file_size for row in entries)<=sum(limits.values()),'archive-total-expanded')
        result={}
        for row in entries:
            mode=(row.external_attr>>16)&0xffff
            _require(not row.is_dir() and not row.flag_bits&1
                and stat.S_IFMT(mode) in (0,stat.S_IFREG)
                and row.compress_type in (zipfile.ZIP_STORED,zipfile.ZIP_DEFLATED),
                'archive-regular-unencrypted')
            _require(0<row.file_size<=limits[row.filename] and 0<row.compress_size<=MAX_ARCHIVE
                and row.file_size<=max(4096,row.compress_size*200),'archive-entry-size')
            with archive.open(row) as stream:value=stream.read(limits[row.filename]+1)
            _require(len(value)==row.file_size,'archive-entry-length')
            result[row.filename]=value
    return result

def read_outcome_archive(raw,expected_sha256,expected_outcomes):
    original=decode_outcome_archive(raw,expected_sha256)
    check_outcome_inventory_bytes(original,expected_outcomes)
    return original
