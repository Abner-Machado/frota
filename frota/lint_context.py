"""frota lint - context budget auditor.

PORTS: context-lint/context_lint.py (v1.0.0 plus the three local fixes)

Public API (do not change):
    run(argv: list[str]) -> int
    lint_file(filepath: str, max_tokens: int = 8000) -> dict

CLI: frota lint <file.md> [--max-tokens N] [--json] [--no-color]
Exit: 0 budget OK or UNLIMITED, 1 over budget, 2 usage or file error.
"""

import json
import re
import sys
from pathlib import Path

from ._tokens import estimate_tokens

USAGE = "Usage: frota lint <file.md> [--max-tokens N] [--json] [--no-color]"

EMPTY_LINE_THRESHOLD = 3
LONG_LINE_CHARS = 200
FILLER_PATTERNS = [
    r"(?i)let me know if you (?:have|need|want)",
    r"(?i)feel free to",
    r"(?i)please (?:note|be aware|keep in mind)",
    r"(?i)it is important to (?:note|mention|remember)",
    r"(?i)as an AI",
    r"(?i)I hope this",
    r"(?i)don't hesitate",
    r"(?i)certainly!",
    r"(?i)of course!",
]


def lint_file(filepath, max_tokens=8000):
    """Lint a prompt file and return a result dict, or {"error": ...}."""
    path = Path(filepath)
    if not path.exists():
        return {"error": "File not found: {0}".format(filepath)}

    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return {"error": "Cannot read {0}: {1}".format(filepath, exc)}

    lines = content.split("\n")
    tokens = estimate_tokens(content)
    over_budget = tokens > max_tokens if max_tokens else None
    waste_percent = 0
    findings = []

    consecutive_empty = 0
    empty_ranges = []
    for i, line in enumerate(lines, 1):
        if line.strip() == "":
            consecutive_empty += 1
        else:
            if consecutive_empty >= EMPTY_LINE_THRESHOLD:
                empty_ranges.append((i - consecutive_empty, i - 1, consecutive_empty))
            consecutive_empty = 0
        if len(line) > LONG_LINE_CHARS:
            findings.append({
                "type": "long_line",
                "severity": "LOW",
                "line": i,
                "message": "Line {0} is {1} chars ({2}+). Consider breaking.".format(
                    i, len(line), LONG_LINE_CHARS),
                "waste_estimate": estimate_tokens(line) - estimate_tokens(line[:LONG_LINE_CHARS]),
            })

    if consecutive_empty >= EMPTY_LINE_THRESHOLD:
        empty_ranges.append((len(lines) - consecutive_empty + 1, len(lines), consecutive_empty))

    wasted_empty_tokens = sum(estimate_tokens("\n" * c) for _, _, c in empty_ranges)

    filler_findings = []
    for pattern in FILLER_PATTERNS:
        for i, line in enumerate(lines, 1):
            if re.search(pattern, line):
                filler_findings.append({
                    "type": "filler_phrase",
                    "severity": "LOW",
                    "line": i,
                    "message": "Filler phrase detected at line {0}".format(i),
                    "snippet": line.strip()[:100],
                })
    findings.extend(filler_findings)

    duplicate_blocks = []
    seen = {}
    entries = [(i + 1, lines[i].strip()) for i in range(len(lines)) if lines[i].strip()]
    block_size = 3
    for start in range(0, len(entries) - block_size + 1):
        block_entries = entries[start:start + block_size]
        block_text = "\n".join(e[1] for e in block_entries)
        if len(block_text) < 40:
            continue
        first_line = block_entries[0][0]
        if block_text in seen:
            duplicate_blocks.append({
                "type": "duplicate_block",
                "severity": "MEDIUM",
                "line": first_line,
                "message": "Duplicate block detected (first seen at line {0})".format(
                    seen[block_text]),
                "snippet": block_text[:80],
                "waste_estimate": estimate_tokens(block_text),
            })
        else:
            seen[block_text] = first_line
    findings.extend(duplicate_blocks)

    waste_tokens = wasted_empty_tokens
    waste_tokens += sum(f["waste_estimate"] for f in findings if "waste_estimate" in f)

    if tokens > 0 and waste_tokens > 0:
        waste_percent = round((waste_tokens / tokens) * 100, 1)

    if max_tokens:
        budget_status = "OVER BUDGET" if over_budget else "OK"
    else:
        budget_status = "UNLIMITED"

    return {
        "file": str(path.absolute()),
        "budget_status": budget_status,
        "max_tokens": max_tokens,
        "estimated_tokens": tokens,
        "waste_tokens": waste_tokens,
        "waste_percent": waste_percent,
        "stats": {
            "total_lines": len(lines),
            "total_chars": len(content),
            "empty_lines": sum(1 for l in lines if l.strip() == ""),
            "long_lines": sum(1 for l in lines if len(l) > LONG_LINE_CHARS),
        },
        "findings": findings,
        "suggestions": [
            "Remove {0} wasted tokens from excessive blank lines".format(wasted_empty_tokens)
            if wasted_empty_tokens > 10 else None,
            "Trim {0} sections with 3+ consecutive blank lines".format(len(empty_ranges))
            if empty_ranges else None,
            "Cut {0} duplicate blocks".format(len(duplicate_blocks))
            if duplicate_blocks else None,
            "Budget: {0}/{1} ({2:.0f}%)".format(
                tokens, max_tokens, (tokens / max_tokens) * 100)
            if max_tokens else "Estimated tokens: {0}".format(tokens),
        ],
    }


def _parse_args(argv):
    filepath = None
    max_tokens = 8000
    as_json = False

    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--json":
            as_json = True
            i += 1
        elif arg == "--no-color":
            # lint output is plain text; the flag is accepted for interface parity.
            i += 1
        elif arg == "--max-tokens":
            if i + 1 >= len(argv):
                raise ValueError("--max-tokens requires a value")
            try:
                max_tokens = int(argv[i + 1])
            except ValueError:
                raise ValueError("invalid --max-tokens value: {0}".format(argv[i + 1]))
            if max_tokens < 0:
                raise ValueError(
                    "invalid --max-tokens value: {0} (must be >= 0, use 0 for no limit)".format(
                        max_tokens))
            i += 2
        elif arg in ("-h", "--help"):
            raise SystemExit(0)
        elif arg.startswith("-"):
            raise ValueError("unknown option: {0}".format(arg))
        else:
            if filepath is not None:
                raise ValueError("expected one file, got extra argument: {0}".format(arg))
            filepath = arg
            i += 1

    if filepath is None:
        raise ValueError("missing <file.md>")

    return filepath, max_tokens, as_json


def run(argv):
    try:
        filepath, max_tokens, as_json = _parse_args(argv)
    except SystemExit:
        print(USAGE)
        return 0
    except ValueError as exc:
        print("frota lint: error: {0}".format(exc), file=sys.stderr)
        print(USAGE, file=sys.stderr)
        return 2

    result = lint_file(filepath, max_tokens)

    if "error" in result:
        print("frota lint: error: {0}".format(result["error"]), file=sys.stderr)
        return 2

    if as_json:
        print(json.dumps(result, indent=2))
    else:
        print("frota lint")
        print("File: {0}".format(result["file"]))
        print("Budget: {0} ({1}/{2} tokens)".format(
            result["budget_status"], result["estimated_tokens"], result["max_tokens"]))
        if result["waste_tokens"] > 0:
            print("Waste: {0} tokens ({1}%)".format(
                result["waste_tokens"], result["waste_percent"]))
        if result["findings"]:
            print("\n--- Findings ({0}) ---".format(len(result["findings"])))
            for f in result["findings"][:20]:
                print("  [{0}] L{1}: {2}".format(f["severity"], f["line"], f["message"]))

    return 0 if result["budget_status"] in ("OK", "UNLIMITED") else 1
