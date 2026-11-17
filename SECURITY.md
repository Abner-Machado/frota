# Security

## Reporting

Use [private vulnerability reporting](https://github.com/Abner-Machado/frota/security/advisories/new)
on this repository, rather than a public issue. No bounty, and no promised response window:
what you get is an honest answer about whether it is real and what happens next.

## What the attack surface actually is

`frota audit` exists to read files written by somebody else. A skill file, a system prompt,
a run log: all of it is untrusted input, and the whole point of the tool is to look at the
dangerous ones. So the surface is parsing, and the failure that matters is a crafted input
that makes the parser do something other than report.

Specifically worth probing:

- A skill or prompt file that makes `audit` or `lint` crash, hang, or exhaust memory
  instead of returning a finding.
- Anything that makes a finding **disappear**: an input carrying an unsafe instruction that
  `audit` reports as clean. A guard that fails open is worse than no guard.
- A path in a JSONL run log that `log` follows outside the directory it was pointed at.

The tool makes no network call, installs nothing, and imports only the standard library,
which CI checks on every push. It does not execute anything it reads.

## What is out of scope

A judgement call about whether a given instruction is unsafe is an issue, not a
vulnerability. The rules are deliberately opinionated and arguing with one is welcome in
the open.
