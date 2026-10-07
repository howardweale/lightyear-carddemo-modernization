"""Offline inventory only. No native dispatch entry point."""
import argparse
import json
from pathlib import Path
from .inventory import inventory, public_summary, summary_markdown

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root",type=Path,required=True,help="Private input directory")
    p.add_argument("--pairs",type=Path,required=True,help="Explicit local pair manifest")
    p.add_argument("--output",type=Path,required=True,help="Fresh local output directory")
    p.add_argument("--scriptdom",nargs="+",help="Trusted installed bridge command; never taken from input SQL")
    a=p.parse_args(argv)
    value=inventory(a.root,json.loads(a.pairs.read_text(encoding="utf-8")),tuple(a.scriptdom) if a.scriptdom else None)
    a.output.mkdir(parents=True,exist_ok=False)
    (a.output/"inventory.private.json").write_text(json.dumps(value,indent=2),encoding="utf-8")
    (a.output/"summary.json").write_text(json.dumps(public_summary(value),indent=2),encoding="utf-8")
    (a.output/"summary.md").write_text(summary_markdown(value),encoding="utf-8")
    print(json.dumps({"pairs":value["pair_count"],"inventory_sha256":value["content_sha256"],"native_cases":0}))
    return 0

if __name__=="__main__": raise SystemExit(main())
