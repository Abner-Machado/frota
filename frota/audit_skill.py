"""frota audit - offline security auditor for AI agent skill files.

PORTS: skill-audit/skill_audit.py (v1.1.0, already fixed)

Public API (do not change):
    run(argv: list[str]) -> int
    audit_file(filepath: str) -> dict

CLI: frota audit <file.md> [--json]
Exit: 0 clean, 1 risks found, 2 usage or file error.
"""

import json
import re
import sys
from pathlib import Path

USAGE = "Usage: frota audit <file.md> [--json]"

RISK_PATTERNS = {
    "eval_injection": {
        "patterns": [r"eval\s*\(", r"exec\s*\("],
        "severity": "CRITICAL",
        "message": "Code execution via eval()/exec() in skill instruction",
        "remediation": "Remove dynamic code execution; use declarative instructions"
    },
    "subprocess_escape": {
        "patterns": [r"subprocess\.", r"os\.system\s*\(", r"os\.popen\s*\("],
        "severity": "CRITICAL",
        "message": "Shell command execution in skill instruction",
        "remediation": "Never call subprocess or os.system from skill instructions"
    },
    "dynamic_import": {
        "patterns": [r"__import__\s*\(", r"importlib\.import_module"],
        "severity": "HIGH",
        "message": "Dynamic module import in skill instruction",
        "remediation": "Use static imports only"
    },
    "file_write": {
        "patterns": [r"open\s*\(.*['\"][wa]", r"Path\(.*\)\.write"],
        "severity": "MEDIUM",
        "message": "File write operation in skill instruction",
        "remediation": "Restrict file writes to approved directories"
    },
    "network_call": {
        "patterns": [r"requests\.", r"urllib\.", r"http\.client", r"fetch\s*\("],
        "severity": "MEDIUM",
        "message": "Network call in skill instruction",
        "remediation": "Prefer local-only operations"
    },
    "credential_leak": {
        "patterns": [r"(?:api[_-]?key|token|secret|password)\s*[:=]\s*['\"]?[a-zA-Z0-9_-]{8,}"],
        "severity": "CRITICAL",
        "message": "Potential hardcoded credential in skill instruction",
        "remediation": "Remove credentials; use environment variables"
    },
    "command_injection": {
        "patterns": [r"os\.system\s*\(.*\$", r"subprocess\.run\s*\(.*shell"],
        "severity": "CRITICAL",
        "message": "Command injection risk in skill instruction",
        "remediation": "Never pass user input to shell commands"
    }
}

# Risks that describe the same underlying danger on a single line. When several
# match the same line we keep the most specific one instead of reporting noise.
EXEC_FAMILY = ("command_injection", "eval_injection", "subprocess_escape")

SEVERITY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}


def audit_file(filepath):
    """Audit a skill file and return a result dict, or {"error": ...}."""
    path = Path(filepath)
    if not path.exists():
        return {"error": "File not found: {0}".format(filepath)}
    if not path.is_file():
        return {"error": "Not a file: {0}".format(filepath)}

    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return {"error": "Cannot read {0}: {1}".format(filepath, exc)}

    lines = content.split("\n")
    stats = {"total_lines": len(lines), "total_chars": len(content)}

    # per_line[line_no][risk_id] = snippet ; keeps one entry per risk per line
    per_line = {}
    for risk_id, risk in RISK_PATTERNS.items():
        for pattern in risk["patterns"]:
            for i, line in enumerate(lines, 1):
                if re.search(pattern, line, re.IGNORECASE):
                    per_line.setdefault(i, {})[risk_id] = line.strip()[:120]

    findings = []
    for line_no in sorted(per_line):
        hits = per_line[line_no]
        exec_hits = [r for r in EXEC_FAMILY if r in hits]
        if len(exec_hits) > 1:
            keep = exec_hits[0]
            others = [r for r in exec_hits[1:]]
            hits = {r: v for r, v in hits.items() if r not in others}
            suffix = ", ".join(RISK_PATTERNS[r]["message"].split(" in ")[0].lower()
                               for r in others)
            hits[keep] = hits[keep] + " [also: {0}]".format(suffix)

        for risk_id, snippet in hits.items():
            risk = RISK_PATTERNS[risk_id]
            findings.append({
                "risk_id": risk_id,
                "severity": risk["severity"],
                "message": risk["message"],
                "line": line_no,
                "snippet": snippet[:120],
                "remediation": risk["remediation"]
            })

    findings.sort(key=lambda f: (SEVERITY_ORDER[f["severity"]], f["line"]))

    summary = {
        "CRITICAL": sum(1 for f in findings if f["severity"] == "CRITICAL"),
        "HIGH": sum(1 for f in findings if f["severity"] == "HIGH"),
        "MEDIUM": sum(1 for f in findings if f["severity"] == "MEDIUM"),
        "LOW": sum(1 for f in findings if f["severity"] == "LOW")
    }

    passed = all(v == 0 for v in summary.values())

    return {
        "file": str(path.absolute()),
        "passed": passed,
        "stats": stats,
        "summary": summary,
        "findings": findings,
        "verdict": "CLEAN" if passed else "RISK FOUND"
    }


def _parse_args(argv):
    filepath = None
    as_json = False

    for arg in argv:
        if arg == "--json":
            as_json = True
        elif arg == "--no-color":
            # audit output is plain text; the flag is accepted for interface parity.
            continue
        elif arg in ("-h", "--help"):
            raise SystemExit(0)
        elif arg.startswith("-"):
            raise ValueError("unknown option: {0}".format(arg))
        else:
            if filepath is not None:
                raise ValueError("expected one file, got extra argument: {0}".format(arg))
            filepath = arg

    if filepath is None:
        raise ValueError("missing <file.md>")

    return filepath, as_json


def run(argv):
    try:
        filepath, as_json = _parse_args(argv)
    except SystemExit:
        print(USAGE)
        return 0
    except ValueError as exc:
        print("frota audit: error: {0}".format(exc), file=sys.stderr)
        print(USAGE, file=sys.stderr)
        return 2

    result = audit_file(filepath)

    if "error" in result:
        print("frota audit: error: {0}".format(result["error"]), file=sys.stderr)
        return 2

    if as_json:
        print(json.dumps(result, indent=2))
    else:
        print("frota audit")
        print("File: {0}".format(result["file"]))
        print("Lines: {0} | Chars: {1}".format(
            result["stats"]["total_lines"], result["stats"]["total_chars"]))
        print("Verdict: {0}".format(result["verdict"]))
        if result["findings"]:
            print("")
            print("--- Findings ---")
            for f in result["findings"]:
                print("  [{0}] L{1}: {2}".format(f["severity"], f["line"], f["message"]))
                print("         -> {0}".format(f["snippet"]))
                print("         Fix: {0}".format(f["remediation"]))
        else:
            print("No risks detected.")

    return 0 if result.get("passed", False) else 1
