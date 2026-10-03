"""Closed built-in feature discovery for the staged console packages.

Requests and local data cannot name importable code. Missing later delivery units
are unavailable, never represented as verified or accepted.
"""

from importlib import import_module, util

MODULES = {
    "campaigns": "campaign_observer",
    "catalogue": "catalogue",
    "workflows": "workflows",
    "workspace": "workspaces",
    "server": "server",
}


def feature(name):
    module = "lightyear_control_tower." + MODULES[name]
    return import_module(module) if util.find_spec(module) else None
