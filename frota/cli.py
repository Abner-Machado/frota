"""Command line entry point. Dispatches to the four frota tools.

Every tool module exposes ``run(argv) -> int`` and prints its own output.
This file owns argument routing only; it must stay free of tool logic.
"""

import sys

from . import __version__

USAGE = """frota {version} - offline toolkit for AI agent prompts and skills

Usage:
  frota <command> [options]

Commands:
  lint <file.md>            Audit a prompt or context file for token waste
  diff <old.md> <new.md>    Compare two prompt versions with token impact
  audit <file.md>           Scan a skill file for unsafe instructions
  log <file.jsonl>          Summarise an agent run log

Options:
  -h, --help                Show help for frota or for a command
  -v, --version             Show version

Exit codes:
  0  clean / within budget
  1  findings, risks or over budget
  2  usage or file error

Run "frota <command> --help" for the options of one command.
""".format(version=__version__)

COMMAND_HELP = {
    "lint": "frota lint <file.md> [--max-tokens N] [--json] [--no-color]",
    "diff": "frota diff <old.md> <new.md> [--context N] [--json] [--no-color]",
    "audit": "frota audit <file.md> [--json]",
    "log": "frota log <file.jsonl> [--json]",
}

# Imported lazily so a broken single tool never takes down the whole CLI.
_COMMANDS = {
    "lint": "lint_context",
    "diff": "diff_prompt",
    "audit": "audit_skill",
    "log": "log",
}


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)

    if not argv or argv[0] in ("-h", "--help", "help"):
        print(USAGE)
        return 0

    if argv[0] in ("-v", "--version", "version"):
        print("frota {0}".format(__version__))
        return 0

    command = argv[0]
    rest = argv[1:]

    if command not in _COMMANDS:
        print("frota: error: unknown command: {0}".format(command), file=sys.stderr)
        print(USAGE, file=sys.stderr)
        return 2

    if rest and rest[0] in ("-h", "--help"):
        print(COMMAND_HELP[command])
        return 0

    module_name = _COMMANDS[command]
    module = __import__("frota." + module_name, fromlist=[module_name])

    try:
        return module.run(rest)
    except BrokenPipeError:
        try:
            sys.stdout.close()
        except Exception:
            pass
        return 0


if __name__ == "__main__":
    sys.exit(main())
