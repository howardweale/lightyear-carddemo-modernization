"""Package the exact imported reader source for the existing single-file mount.

No native launch or policy rewrite. The controller's frozen import/source checks
bind these modules before preparation. The generated file contains the shared
implementation bytes verbatim and the unchanged B06 policy wrapper.
"""
from pathlib import Path
from lightyear_evidence import content
from . import bundle_content


def reader_bytes():
    core = Path(content.__file__).read_bytes()
    adapter = Path(bundle_content.__file__).read_text(encoding="utf-8")
    declaration = "from lightyear_evidence.content import content_view, safe, stream_hash, require"
    selector = "from lightyear_evidence.content import excluded as select"
    if adapter.count(declaration) != 1 or adapter.count(selector) != 1:
        raise ValueError("standalone-reader-import-shape")
    header = ("import types\n_core=types.ModuleType('lightyear_evidence.content')\n"
              + "exec(compile(" + repr(core) + ", 'lightyear_evidence/content.py', 'exec'), _core.__dict__)\n"
              + "content_view, safe, stream_hash, require = (_core.content_view, _core.safe, _core.stream_hash, _core.require)")
    return adapter.replace(declaration, header).replace(selector, "select = _core.excluded").encode("utf-8")
