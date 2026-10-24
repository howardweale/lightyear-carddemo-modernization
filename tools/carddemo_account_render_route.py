"""Closed, source-bound rendering composition; existing earlier routes stay in their own guards."""
from hashlib import sha256
from pathlib import Path
import re
JAVA='factory/carddemo-web/service/src/main/java/ai/lightyear/carddemo/'
MODELS={'AccountMapModel.java': '8944014de4abdca25cbfcb812536dc3b7a8a1230d1c26aac0aa1b1fb370b50ae', 'AccountRenderModel.java': '9ce993d8e31f94f8276a5be81c9f754ceeb9033e42dde3615b1e872f1a40786a'}
BODY='SourceEdits e=new SourceEdits(AccountRenderModel.retire(bindings.root.path("account_update").path("validation")),bindings.clock);e.loadArea(area);return e;'
def check_render_route(root,service):
    # Remove comments but retain literals so a commented-out call cannot serve as proof.
    code=re.sub(r'"(?:\\.|[^"\\])*"|/\*[\s\S]*?\*/|//[^\n]*',lambda m:m[0] if m[0].startswith('"') else ' ',service)
    bodies=re.findall(r'private SourceEdits edits\(Commarea area\)\{([^{}]*)\}',code)
    if bodies!=[BODY]:raise ValueError('render-service-routing')
    for name,digest in MODELS.items():
        path=Path(root)/JAVA/name
        if not path.is_file() or sha256(path.read_bytes().replace(b'\r\n',b'\n')).hexdigest()!=digest:
            raise ValueError('render-composed-model-binding')
