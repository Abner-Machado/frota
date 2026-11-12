# frota

Offline toolkit for AI agent prompts and skills. One command, four jobs:

- **lint** — context budget audit: token count, wasted space, duplicate blocks
- **diff** — compare two prompt versions with token impact per change
- **audit** — scan a skill file for unsafe instructions
- **log** — agent run logger, plus a summary of any JSONL run log

Zero dependencies. Python 3.8+. Nothing leaves your machine.

## Why one package

These started as four separate repositories. Keeping them apart meant four installs,
four READMEs, four different flag styles and four copies of the same token estimator.
They belong together: you lint a prompt, diff the next version, audit the skill that
uses it, and read the run log when the agent misbehaves.

## Install

```bash
pip install frota
```

Or from source:

```bash
git clone https://github.com/Abner-Machado/frota
cd frota
pip install .
```

## Usage

```bash
frota lint system-prompt.md
frota diff old-prompt.md new-prompt.md --context 3
frota audit skills/web-search/SKILL.md
frota log runs/2026-11-11.jsonl
```

Every command has `--json` for machine output. Use `--no-color` in CI.

### frota lint

Estimates the token cost of a prompt file and points at waste: runs of blank lines,
filler phrases, duplicated blocks, lines long enough to hide a whole instruction.

```bash
frota lint context.md --max-tokens 8000
```

| Flag | Meaning |
|---|---|
| `--max-tokens N` | Budget in tokens. Omit for no limit. |
| `--json` | Machine-readable output |
| `--no-color` | Disable ANSI colors |

Exit code is `1` when the file is over budget, `0` when it fits.

### frota diff

Line-by-line comparison with the token cost of each change, so you can see whether a
rewrite actually saved context or just moved words around.

```bash
frota diff old.md new.md --context 2
```

| Flag | Meaning |
|---|---|
| `--context N` | Show N lines around each change (default 2) |
| `--json` | Machine-readable output |
| `--no-color` | Disable ANSI colors |

Flags may come before or after the file paths: `frota diff --context 1 a.md b.md` works.

### frota audit

Scans a skill or prompt file for instructions that can hurt an agent: `eval`/`exec`,
shell execution, dynamic imports, file writes, network calls and hardcoded credentials.

```bash
frota audit SKILL.md
frota audit SKILL.md --json
```

Each finding carries a severity, the line, a snippet and a remediation. One line
produces one finding: overlapping shell risks are merged, not reported twice.
Exit code is `1` when anything is found.

### frota log

A small logger for agent runs, and a reader for what it writes.

```python
from frota.log import create_logger

log = create_logger(output="runs/today.jsonl", level="info", trace=True)
log.info("tool_call", {"tool": "search"})
log.step("fetch", {"tokens": 1200, "duration_ms": 840})
log.error("parse failed", ValueError("bad json"))
log.summary()
log.close()
```

Then summarise the run:

```bash
frota log runs/today.jsonl
frota log runs/today.jsonl --json
```

The summary reports total steps, errors, tokens, duration and the time window.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | clean, or within budget |
| 1 | findings, risks, or over budget |
| 2 | usage error or unreadable file |

## Design notes

- Token counts are estimates at about four characters per token. Good enough to compare
  versions and catch waste, not a substitute for a real tokenizer.
- The audit is pattern based. It finds instruction text that looks dangerous; it does not
  execute anything and cannot prove a skill is safe.
- Nothing is uploaded. No network code exists in the package.

## License

MIT. See [LICENSE](LICENSE).
