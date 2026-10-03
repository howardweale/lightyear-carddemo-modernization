"""Locally administered trust, kept outside the engine-writable data root."""

from pathlib import Path
from .requests import read_json, read_bytes


def qualification_key(root, config, *, scope=None):
    root = Path(root).resolve()
    config = Path(config).resolve()
    if config.is_relative_to(root):
        raise ValueError("Qualification trust must be outside the engine data root")
    value = read_json(config)
    if scope is not None and value.get("scope") != scope:
        raise ValueError("Wrong qualification trust scope")
    path = (config.parent / value["public_key"]).resolve()
    if path.is_relative_to(root):
        raise ValueError("Qualification key must be outside the engine data root")
    return read_bytes(path)
