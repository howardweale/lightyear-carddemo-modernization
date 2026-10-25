"""CI-only exact rendering composition and decoy/refusal checks."""
from pathlib import Path
import tempfile,unittest
from tools.carddemo_account_render_route import JAVA,MODELS,check_render_route
ROOT=Path(__file__).resolve().parents[1]
class RenderRouteTests(unittest.TestCase):
    def test_exact_chain_and_missing_changed_discarded_or_decoy_routes(self):
        service=(ROOT/JAVA/'AccountUpdateService.java').read_text()
        check_render_route(ROOT,service)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/JAVA).mkdir(parents=True)
            originals={name:(ROOT/JAVA/name).read_bytes().replace(b'\r\n',b'\n') for name in MODELS}
            with self.assertRaises(ValueError):check_render_route(root,service)
            for name,raw in originals.items():(root/JAVA/name).write_bytes(raw)
            check_render_route(root,service)
            for name,raw in originals.items():
                (root/JAVA/name).write_bytes(raw.replace(b'\n',b'\r\n'));check_render_route(root,service)
                for bad in (raw+b'// decoy\n',raw.replace(b'return model;',b'return original;'),raw.replace(b'retire(original)',b'retire(original.deepCopy())')):
                    self.assertNotEqual(raw,bad);(root/JAVA/name).write_bytes(bad)
                    with self.subTest(model=name),self.assertRaises(ValueError):check_render_route(root,service)
                (root/JAVA/name).write_bytes(raw)
            method=next(line for line in service.splitlines() if 'private SourceEdits edits(' in line)
            for bad in (service.replace('AccountRenderModel.retire','AccountMapModel.retire'),
                        service.replace('path("validation")','path("other")'),
                        service.replace('e.loadArea(area);return e;','return new SourceEdits(null,bindings.clock);'),
                        '/*'+method+'*/',service.replace(method,'//'+method),service+'\n'+service):
                self.assertNotEqual(service,bad)
                with self.subTest(service=bad),self.assertRaises(ValueError):check_render_route(root,bad)
