"""Selected module origin/file checks, not loaded-code or workflow attestation.

The fixed module set covers the review's direct helpers and native entry modules.
It is not a transitive import/callgraph inventory. Module metadata and source
files do not prove in-memory callable identity, Python/package integrity, or
absence of TOCTOU changes. No publication or execution authority is returned.
"""
from hashlib import sha256
import os,re,stat,sys,types
from pathlib import Path
from tools.ci.operator_flow_consumer import clean_root,git
from tools.ci.operator_flow_metadata import require

MODULES=(
    ('tools.ci.operator_flow_publication_review','tools/ci/operator_flow_publication_review.py'),
    ('tools.ci.operator_flow_review_source','tools/ci/operator_flow_review_source.py'),
    ('tools.ci.operator_flow_handoff','tools/ci/operator_flow_handoff.py'),
    ('tools.ci.operator_flow_download','tools/ci/operator_flow_download.py'),
    ('tools.ci.operator_flow_consumer','tools/ci/operator_flow_consumer.py'),
    ('tools.ci.operator_flow_metadata','tools/ci/operator_flow_metadata.py'),
    ('tools.ci.operator_flow_publication_reconstruction','tools/ci/operator_flow_publication_reconstruction.py'),
    ('tools.ci.operator_flow_publication_objects','tools/ci/operator_flow_publication_objects.py'),
    ('lightyear_factory.contracts','src/lightyear_factory/contracts.py'),
    ('lightyear_factory.model_admission','src/lightyear_factory/model_admission.py'),
    ('lightyear_execution.contracts','src/lightyear_execution/contracts.py'),
    ('lightyear_execution.tower_drill_admission','src/lightyear_execution/tower_drill_admission.py'),
    ('lightyear_execution.tower_drill_reservation','src/lightyear_execution/tower_drill_reservation.py'),
)
LIMIT=4*1024*1024


def _source_bytes(path):
    path=Path(path)
    require(path.is_absolute() and path.resolve(strict=True)==path,'review-source-absolute')
    for part in (path,*path.parents):
        require(not part.is_symlink() and not getattr(part.lstat(),'st_file_attributes',0)&0x400,
            'review-source-reparse')
    before=path.stat()
    require(stat.S_ISREG(before.st_mode) and before.st_nlink==1
        and 0<before.st_size<=LIMIT,'review-source-file')
    with path.open('rb') as stream:
        opened=os.fstat(stream.fileno());raw=stream.read(LIMIT+1);after=os.fstat(stream.fileno())
    def identity(s):return (s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
    require(identity(before)==identity(opened)==identity(after)==identity(path.stat())
        and len(raw)==before.st_size,'review-source-changed')
    return raw


def check_review_source(root,executable):
    require(os.environ.get('GITHUB_ACTIONS')=='true','review-source-ci-only')
    require(type(executable) is str and re.fullmatch('[0-9a-f]{40}',executable),'review-source-head-shape')
    root=Path(root);clean_root(root)
    require(git(root,'rev-parse','HEAD').decode().strip()==executable,'review-source-exact-E')
    observed={}
    for name,relative in MODULES:
        module=sys.modules.get(name);path=root/relative
        require(type(module) is types.ModuleType,'review-source-module-missing')
        spec=getattr(module,'__spec__',None)
        origins=(getattr(module,'__file__',None),getattr(spec,'origin',None))
        require(all(type(value) is str and Path(value).is_absolute() and Path(value)==path
            for value in origins),'review-source-module-origin')
        raw=_source_bytes(path)
        # Read the committed blob only after its native size check. This does
        # not impose a general bound on Git process output or process creation.
        ref=executable+':'+relative
        size=git(root,'cat-file','-s',ref).decode().strip()
        require(re.fullmatch('[1-9][0-9]{0,7}',size) and int(size)<=LIMIT,'review-source-blob-size')
        original=git(root,'show',ref)
        require(len(original)==int(size) and raw==original,'review-source-committed-bytes')
        observed[name]=sha256(raw).hexdigest()
    clean_root(root)
    require(git(root,'rev-parse','HEAD').decode().strip()==executable,'review-source-head-changed')
    return observed
