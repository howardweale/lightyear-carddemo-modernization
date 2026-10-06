"""CI/read-only guard for the isolated Verify graph increment."""
import argparse
import subprocess


def protected(path):
    return (path.startswith(("tools/ms94_b06_", "tools/ms94_builder_mcp",
                             "tools/journey_builder_mcp.py", "work/ms94/"))
            or "/template-r1/" in path or "/stage-b-05/" in path
            or path.startswith("src/lightyear_control_tower/b06"))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--base",required=True)
    args=p.parse_args()
    paths=subprocess.check_output(["git","diff","--name-only",args.base,"--"],text=True).splitlines()
    refused=[path for path in paths if protected(path)]
    if refused: raise SystemExit("Protected paths changed: "+", ".join(refused))
    print("Verify graph diff: no B05/B06/template-r1/work-ms94 changes")


if __name__=="__main__": main()
