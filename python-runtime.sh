#!/usr/bin/env bash

lightyear_resolve_python() {
  local candidate=""
  local resolved=""
  local version=""
  local candidates=()

  if [[ -n "${LIGHTYEAR_PYTHON:-}" ]]; then
    candidates=("$LIGHTYEAR_PYTHON")
  else
    candidates=(python3.14 python3.13 python3.12 python3.11 python3)
  fi

  for candidate in "${candidates[@]}"; do
    if ! resolved="$(command -v "$candidate" 2>/dev/null)"; then
      continue
    fi
    if "$resolved" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' \
      >/dev/null 2>&1; then
      version="$("$resolved" -c 'import sys; print(".".join(map(str, sys.version_info[:3])))')"
      LIGHTYEAR_PYTHON_BIN="$resolved"
      export LIGHTYEAR_PYTHON_BIN
      echo "Using Python $version: $LIGHTYEAR_PYTHON_BIN"
      return 0
    fi
  done

  echo "LIGHTYEAR requires Python 3.11 or newer." >&2
  echo "Apple's /usr/bin/python3 is Python 3.9 and is not supported." >&2
  echo "Install a current Python from https://www.python.org/downloads/macos/" >&2
  echo "or set LIGHTYEAR_PYTHON to a supported executable." >&2
  return 2
}
