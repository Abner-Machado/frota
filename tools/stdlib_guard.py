#!/usr/bin/env python3
"""Fail if anything in this repository imports outside the standard library.

The claim "no install, no network, no dependencies" is in the README. A static badge
asserting it is worth nothing, so this checks it instead, and CI fails when it stops being
true. The allowed set comes from the running interpreter, not from a list someone has to
remember to update.

    python tools/stdlib_guard.py                      # everything, stdlib only
    python tools/stdlib_guard.py src                  # runtime code only
    python tools/stdlib_guard.py . --allow pytest     # a declared test-only dependency
    python tools/stdlib_guard.py . --skip tests       # same thing, by directory

An exemption is printed every run. A dependency that is allowed in silence is a dependency
nobody remembers agreeing to.
"""

from __future__ import annotations

import argparse
import ast
import os
import sys

SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", "node_modules", "site-packages",
             "build", "dist", ".mypy_cache", ".pytest_cache"}


SOURCE_ROOTS = ("src", "lib")


def _names_in(directory):
    names = set()
    if not os.path.isdir(directory):
        return names
    for entry in os.listdir(directory):
        if entry in SKIP_DIRS:
            continue
        path = os.path.join(directory, entry)
        if entry.endswith(".py"):
            names.add(entry[:-3])
        elif os.path.isdir(path) and os.path.exists(os.path.join(path, "__init__.py")):
            names.add(entry)
    return names


def local_modules(root):
    """Names importable from inside the repo itself, which are never a dependency.

    A src layout counts: with `src/pkg/__init__.py`, a test that does `import pkg` is
    importing this repository, not a dependency.
    """
    names = _names_in(root)
    for source_root in SOURCE_ROOTS:
        names |= _names_in(os.path.join(root, source_root))
    return names


IMPORT_ERRORS = {"ImportError", "ModuleNotFoundError"}


def _catches_import_error(handler):
    name = handler.type
    if name is None:  # bare except, which does catch it
        return True
    if isinstance(name, ast.Name):
        return name.id in IMPORT_ERRORS
    if isinstance(name, ast.Tuple):
        return any(isinstance(e, ast.Name) and e.id in IMPORT_ERRORS for e in name.elts)
    return False


def _guarded_lines(tree):
    """Lines sitting inside a try whose except catches a missing module.

    An import written that way is an optional dependency with a fallback, which is the
    normal way to use tomli on 3.10 or a faster parser when it happens to be installed.
    Failing a build over one would be the guard crying wolf.
    """
    lines = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Try) and any(_catches_import_error(h) for h in node.handlers):
            for child in ast.walk(node):
                if isinstance(child, (ast.Import, ast.ImportFrom)):
                    lines.add(child.lineno)
    return lines


def imported_modules(path):
    """Every top-level module imported by one file, as (module, line, optional)."""
    with open(path, encoding="utf-8") as fh:
        try:
            tree = ast.parse(fh.read(), filename=path)
        except SyntaxError as exc:
            print(f"stdlib-guard: cannot parse {path}: {exc}", file=sys.stderr)
            return []
    guarded = _guarded_lines(tree)
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.append((alias.name.split(".")[0], node.lineno, node.lineno in guarded))
        elif isinstance(node, ast.ImportFrom):
            # A relative import never leaves the repository.
            if node.level == 0 and node.module:
                found.append((node.module.split(".")[0], node.lineno, node.lineno in guarded))
    return found


def main(argv=None):
    ap = argparse.ArgumentParser(prog="stdlib_guard.py", description=__doc__.splitlines()[0])
    ap.add_argument("path", nargs="?", default=".", help="directory to check (default .)")
    ap.add_argument("--allow", action="append", default=[], metavar="MODULE",
                    help="permit this non-stdlib module, e.g. a declared test dependency. "
                         "Repeatable, and every use is printed")
    ap.add_argument("--skip", action="append", default=[], metavar="DIR",
                    help="skip this directory name entirely. Repeatable")
    args = ap.parse_args(argv)

    root = os.path.abspath(args.path)
    if not os.path.isdir(root):
        sys.exit(f"stdlib-guard: {root} is not a directory")

    skip = SKIP_DIRS | set(args.skip)
    allowed = set(sys.stdlib_module_names) | local_modules(root) | {"__future__"}
    exempt = set(args.allow)
    offenders, used_exemptions, optional = [], {}, {}
    checked = 0

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in skip]
        for name in sorted(filenames):
            if not name.endswith(".py"):
                continue
            path = os.path.join(dirpath, name)
            checked += 1
            rel = os.path.relpath(path, root).replace(os.sep, "/")
            for module, line, is_optional in imported_modules(path):
                if module in allowed:
                    continue
                if is_optional:
                    optional.setdefault(module, []).append(f"{rel}:{line}")
                    continue
                if module in exempt:
                    used_exemptions.setdefault(module, []).append(f"{rel}:{line}")
                    continue
                offenders.append((rel, line, module))

    for module in sorted(optional):
        where = optional[module]
        print(f"stdlib-guard: {module} is optional, behind a try/except on a missing module "
              f"({where[0]})")
    for module in sorted(used_exemptions):
        where = used_exemptions[module]
        print(f"stdlib-guard: allowing {module} ({len(where)} import(s), first {where[0]})")
    for module in sorted(exempt - set(used_exemptions)):
        print(f"stdlib-guard: --allow {module} was passed and never used. Drop it")

    if offenders:
        print(f"stdlib-guard: {len(offenders)} import(s) outside the standard library")
        for rel, line, module in offenders:
            print(f"  {rel}:{line}  {module}")
        print("\nThe README claims this runs with no install. Either the claim or the import "
              "has to go.")
        return 1

    print(f"stdlib-guard: {checked} file(s) checked, every import is standard library "
          f"or allowed (Python {sys.version_info.major}.{sys.version_info.minor})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
