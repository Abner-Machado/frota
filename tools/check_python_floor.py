#!/usr/bin/env python3
"""Fail if the code uses syntax newer than the Python floor declared in pyproject.toml.

`requires-python = ">=3.8"` is a promise to anyone on 3.8. CI cannot easily run every
interpreter that old, but the syntax half of the promise is checkable right here: ast can
parse a file as a chosen language version and refuse what came later.

What this proves: no walrus in 3.7, no match in 3.9, no `X | None` annotation in 3.9.
What it does not prove: that a 3.8 interpreter has every library function used at runtime.
Only running 3.8 proves that, so the floor stays a claim about syntax until it does.

    python tools/check_python_floor.py
    python tools/check_python_floor.py --floor 3.9
"""

from __future__ import annotations

import argparse
import ast
import os
import re
import sys

SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", "node_modules", "build", "dist",
             ".mypy_cache", ".pytest_cache"}
FLOOR_RE = re.compile(r"""requires-python\s*=\s*["'][^0-9]*(\d+)\.(\d+)""")


def declared_floor(root):
    path = os.path.join(root, "pyproject.toml")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        match = FLOOR_RE.search(fh.read())
    return (int(match.group(1)), int(match.group(2))) if match else None


def main():
    ap = argparse.ArgumentParser(prog="check_python_floor.py",
                                 description=__doc__.splitlines()[0])
    ap.add_argument("path", nargs="?", default=".")
    ap.add_argument("--floor", metavar="X.Y",
                    help="override the floor instead of reading pyproject.toml")
    args = ap.parse_args()

    root = os.path.abspath(args.path)
    if args.floor:
        major, minor = (int(p) for p in args.floor.split(".", 1))
    else:
        floor = declared_floor(root)
        if floor is None:
            sys.exit("check_python_floor: no requires-python in pyproject.toml, and no "
                     "--floor given. Declare the floor or pass it")
        major, minor = floor

    if (major, minor) > sys.version_info[:2]:
        sys.exit(f"check_python_floor: this interpreter is {sys.version_info.major}."
                 f"{sys.version_info.minor} and cannot check a {major}.{minor} floor")

    failures, checked = [], 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in sorted(filenames):
            if not name.endswith(".py"):
                continue
            path = os.path.join(dirpath, name)
            rel = os.path.relpath(path, root).replace(os.sep, "/")
            checked += 1
            with open(path, encoding="utf-8") as fh:
                source = fh.read()
            try:
                ast.parse(source, filename=path, feature_version=(major, minor))
            except SyntaxError as exc:
                failures.append((rel, exc.lineno, str(exc).split(" (", 1)[0]))

    if failures:
        print(f"check_python_floor: {len(failures)} file(s) need syntax newer than "
              f"{major}.{minor}, which pyproject.toml promises to support")
        for rel, line, why in failures:
            print(f"  {rel}:{line}  {why}")
        print("\nEither raise requires-python or stop using that syntax.")
        return 1

    print(f"check_python_floor: {checked} file(s) parse as Python {major}.{minor}, "
          f"the declared floor")
    return 0


if __name__ == "__main__":
    sys.exit(main())
