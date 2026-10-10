"""Explicit host JDK tools; never fall back to a different PATH toolchain."""
import os
from pathlib import Path


def executable(jdk, name):
    if name not in {'java', 'javac', 'jlink', 'jcmd'}:
        raise ValueError('host-jdk-tool-not-allowed')
    path = Path(jdk)/'bin'/(name + ('.exe' if os.name == 'nt' else ''))
    if not path.is_file():
        raise ValueError('host-jdk-tool-missing: ' + str(path))
    return path
