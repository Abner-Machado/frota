"""frota diff - compare two prompt versions with token impact.

Ported from prompt-diff v1.1.0.

Public API:
    run(argv: list[str]) -> int
    diff_prompts(old_lines, new_lines) -> (changes, stats)
"""

import sys
import difflib
import json
from pathlib import Path

from . import __version__
from ._tokens import estimate_tokens

RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
RESET = "\033[0m"
BOLD = "\033[1m"

USAGE = "frota diff <old.md> <new.md> [--context N] [--json] [--no-color]"


def load_file(filepath):
    path = Path(filepath)
    if not path.exists():
        return None, "File not found: {0}".format(filepath)
    if not path.is_file():
        return None, "Not a file: {0}".format(filepath)
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return None, "Cannot read {0}: {1}".format(filepath, exc)
    return text.splitlines(), None


def diff_prompts(old_lines, new_lines):
    sm = difflib.SequenceMatcher(None, old_lines, new_lines)
    changes = []
    stats = {"added": 0, "removed": 0, "modified": 0}

    def add_change(kind, old_no, new_no, old_text, new_text, token_delta):
        changes.append({
            "type": kind,
            "old_line": old_no,
            "new_line": new_no,
            "old_text": old_text,
            "new_text": new_text,
            "token_delta": token_delta,
        })
        stats[kind] += 1

    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue

        old_block = old_lines[i1:i2]
        new_block = new_lines[j1:j2]

        if tag == "insert":
            for k, line in enumerate(new_block, j1 + 1):
                add_change("added", None, k, None, line.strip()[:120],
                           estimate_tokens(line))
        elif tag == "delete":
            for k, line in enumerate(old_block, i1 + 1):
                add_change("removed", k, None, line.strip()[:120], None,
                           -estimate_tokens(line))
        elif tag == "replace":
            common = min(len(old_block), len(new_block))
            for k in range(common):
                old_line = old_block[k]
                new_line = new_block[k]
                delta = estimate_tokens(new_line) - estimate_tokens(old_line)
                add_change("modified", i1 + k + 1, j1 + k + 1,
                           old_line.strip()[:120], new_line.strip()[:120], delta)
            for k in range(common, len(old_block)):
                add_change("removed", i1 + k + 1, None,
                           old_block[k].strip()[:120], None,
                           -estimate_tokens(old_block[k]))
            for k in range(common, len(new_block)):
                add_change("added", None, j1 + k + 1,
                           None, new_block[k].strip()[:120],
                           estimate_tokens(new_block[k]))

    return changes, stats


def _print_context(side, lines, line_no, context, color, no_color):
    if line_no is None:
        return
    reset = "" if no_color else RESET
    start = max(0, line_no - 1 - context)
    end = min(len(lines), line_no - 1 + context + 1)
    for idx in range(start, end):
        print("    {0}{1} L{2}: {3}{4}".format(
            color, side, idx + 1, lines[idx].strip()[:80], reset))


def print_diff(changes, old_tokens, new_tokens, old_lines, new_lines, context, no_color):
    red = "" if no_color else RED
    green = "" if no_color else GREEN
    yellow = "" if no_color else YELLOW
    cyan = "" if no_color else CYAN
    bold = "" if no_color else BOLD
    reset = "" if no_color else RESET

    delta = new_tokens - old_tokens
    pct = abs(delta) / max(1, old_tokens) * 100
    sign = "+" if delta >= 0 else ""

    print("Old: {0} tokens -> New: {1} tokens".format(old_tokens, new_tokens))
    print("Delta: {0}{1}{2} tokens ({3}{4:.1f}%){5}".format(
        bold, sign, delta, sign, pct, reset))
    print()

    if not changes:
        print("{0}No changes detected.{1}".format(green, reset))
        return

    added_count = sum(1 for c in changes if c["type"] == "added")
    removed_count = sum(1 for c in changes if c["type"] == "removed")
    modified_count = sum(1 for c in changes if c["type"] == "modified")
    print("{0}--- Changes ({1} added, {2} removed, {3} modified) ---{4}".format(
        cyan, added_count, removed_count, modified_count, reset))
    print()

    for c in changes:
        if c["type"] == "added":
            if context > 0:
                _print_context("new", new_lines, c["new_line"], context, green, no_color)
            print("  {0}+ L{1} (+{2} tok){3}: \"{4}\"".format(
                green, c["new_line"], c["token_delta"], reset, c["new_text"]))
        elif c["type"] == "removed":
            if context > 0:
                _print_context("old", old_lines, c["old_line"], context, red, no_color)
            print("  {0}- L{1} ({2} tok){3}: \"{4}\"".format(
                red, c["old_line"], c["token_delta"], reset, c["old_text"]))
        elif c["type"] == "modified":
            if context > 0:
                _print_context("old", old_lines, c["old_line"], context, red, no_color)
                _print_context("new", new_lines, c["new_line"], context, green, no_color)
            sign2 = "+" if c["token_delta"] >= 0 else ""
            print("  {0}~ L{1} ({2}{3} tok){4}: \"{5}\" -> \"{6}\"".format(
                yellow, c["old_line"], sign2, c["token_delta"], reset,
                c["old_text"], c["new_text"]))

    print()
    savings = delta * -1
    cost_usd = savings * 0.000002
    if savings > 0:
        line = "{0}Saved {1} tokens.{2}".format(green, savings, reset)
        if cost_usd >= 0.001:
            line += " {0}That's about ${1:.4f} at GPT-4o pricing.{2}".format(
                cyan, cost_usd, reset)
        print(line)
    elif savings < 0:
        print("{0}Added {1} tokens.{2}".format(yellow, abs(savings), reset))


def parse_args(argv):
    files = []
    opts = {"json": False, "no_color": False, "context": 2}
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--json":
            opts["json"] = True
            i += 1
        elif arg in ("--no-color", "--no-colour"):
            opts["no_color"] = True
            i += 1
        elif arg == "--context" or arg.startswith("--context="):
            if arg.startswith("--context="):
                raw = arg.split("=", 1)[1]
                i += 1
            else:
                if i + 1 >= len(argv):
                    raise ValueError("--context requires a value")
                raw = argv[i + 1]
                i += 2
            try:
                value = int(raw)
            except ValueError:
                raise ValueError("invalid --context value: {0}".format(raw))
            if value < 0:
                raise ValueError("invalid --context value: {0} (must be >= 0)".format(raw))
            opts["context"] = value
        elif arg.startswith("-"):
            raise ValueError("unknown option: {0}".format(arg))
        else:
            files.append(arg)
            i += 1
    return files, opts


def run(argv):
    argv = list(argv)

    try:
        files, opts = parse_args(argv)
    except ValueError as exc:
        print("frota diff: error: {0}".format(exc), file=sys.stderr)
        print(USAGE, file=sys.stderr)
        return 2

    if len(files) != 2:
        print(USAGE, file=sys.stderr)
        return 2

    old_path, new_path = files

    old_lines, err = load_file(old_path)
    if err:
        print(err, file=sys.stderr)
        return 2

    new_lines, err = load_file(new_path)
    if err:
        print(err, file=sys.stderr)
        return 2

    old_text = "\n".join(old_lines)
    new_text = "\n".join(new_lines)
    old_tokens = estimate_tokens(old_text)
    new_tokens = estimate_tokens(new_text)

    changes, stats = diff_prompts(old_lines, new_lines)

    if opts["json"]:
        result = {
            "version": __version__,
            "old_file": old_path,
            "new_file": new_path,
            "old_tokens": old_tokens,
            "new_tokens": new_tokens,
            "token_delta": new_tokens - old_tokens,
            "change_pct": round(abs(new_tokens - old_tokens) / max(1, old_tokens) * 100, 1),
            "stats": stats,
            "changes": changes,
        }
        print(json.dumps(result, indent=2))
    else:
        print_diff(changes, old_tokens, new_tokens, old_lines, new_lines,
                   opts["context"], opts["no_color"])

    return 0
