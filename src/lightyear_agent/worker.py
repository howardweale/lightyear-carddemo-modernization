"""Detached worker: the MCP client's lifetime never owns the engine process."""
import argparse
from pathlib import Path
from .service import Workflow


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    Workflow(args.project).work(args.run_id)


if __name__ == "__main__":
    main()
