"""Fail if a closed Tower route, navigation tab or decision kind is undocumented."""
import ast
import re
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def vocabulary(root=ROOT):
    root=Path(root)
    server=ast.parse((root/"src/lightyear_control_tower/server.py").read_text(encoding="utf-8"))
    routes={"session"}
    for node in server.body:
        if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id in {"READ_ROUTES","WRITE_ROUTES"} for t in node.targets):
            routes.update(ast.literal_eval(node.value.args[0]))
    tabs=re.findall(r'data-tab="([^"]+)"[^>]*>([^<]+)',(root/"knowledge/viewer/decision-console.html").read_text(encoding="utf-8"))
    kinds=set()
    tree=ast.parse((root/"src/lightyear_control_tower/kinds.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id in {"K","DecisionKind"} and node.args and isinstance(node.args[0],ast.Constant):
            kinds.add(node.args[0].value)
        if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=="specs" for t in node.targets):
            kinds.update(ast.literal_eval(node.value))
    tree=ast.parse((root/"src/lightyear_control_tower/carddemo_policy.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=="KINDS" for t in node.targets): kinds.update(ast.literal_eval(node.value))
    return sorted("/api/tower/"+r for r in routes),tabs,sorted(kinds)


def check(root=ROOT):
    text=(Path(root)/"docs/control-tower-users-manual.md").read_text(encoding="utf-8")
    routes,tabs,kinds=vocabulary(root)
    expected=routes+[label for _,label in tabs]+kinds
    missing=[value for value in expected if not re.search(r"(?<![\w/-])"+re.escape(value)+r"(?![\w/-])",text)]
    missing += ["tab:"+key for key,_ in tabs if "`"+key+"`" not in text]
    if missing:raise ValueError("Tower manual missing: "+", ".join(missing))
    return dict(routes=len(routes),tabs=len(tabs),kinds=len(kinds))


if __name__=="__main__":print(check())
