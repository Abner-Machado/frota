"""frota log - agent run logger with a JSONL summary command.

Python port of agent-log v1.0.0 (JavaScript).

Public API:
    run(argv: list[str]) -> int
    create_logger(output="stdout", format="json", level="info", trace=False) -> Logger
"""

import json
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

LEVELS = {"debug": 10, "info": 20, "warn": 30, "error": 40}

USAGE = "frota log <file.jsonl> [--json]"


def _iso_from_ms(ms):
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc).isoformat().replace(
        "+00:00", "Z")


class Logger(object):
    """Writes one JSON object (or one text line) per event."""

    def __init__(self, output="stdout", format="json", level="info", trace=False):
        self.format = format if format in ("json", "text") else "json"
        self.trace = bool(trace)
        self.threshold = LEVELS.get(level, LEVELS["info"])
        self._own_stream = False
        self._closed = False

        if output == "stderr":
            self.stream = sys.stderr
        elif output in ("stdout", None, ""):
            self.stream = sys.stdout
        else:
            try:
                self.stream = open(output, "a", encoding="utf-8")
                self._own_stream = True
            except OSError as exc:
                sys.stderr.write(
                    "[frota.log] cannot open {0}: {1}; falling back to stderr\n".format(
                        json.dumps(str(output)), exc))
                self.stream = sys.stderr
                self._own_stream = False

        self.start = int(time.time() * 1000)
        self.start_time = _iso_from_ms(self.start)
        self.steps = 0
        self.errors = 0
        self.total_tokens = 0
        self.total_duration_ms = 0

    def _write_line(self, line):
        if self._closed:
            return
        try:
            self.stream.write(line + "\n")
            self.stream.flush()
        except Exception:
            if self.stream is not sys.stderr:
                self.stream = sys.stderr
                sys.stderr.write("[frota.log] write failed; falling back to stderr\n")
                sys.stderr.write(line + "\n")

    def _emit_record(self, record):
        if self.format == "json":
            self._write_line(json.dumps(record, default=str))
        else:
            payload = json.dumps(record.get("data", {}), default=str)
            self._write_line("{0} [{1}] {2} {3}".format(
                record["ts"], record["level"].upper(), record["action"], payload))

    def _event(self, level_name, action, data):
        if LEVELS[level_name] < self.threshold:
            return
        self._emit_record({
            "ts": _iso_from_ms(int(time.time() * 1000)),
            "level": level_name,
            "action": str(action),
            "data": data if data is not None else {},
        })

    def debug(self, action, data=None):
        self._event("debug", action, data)

    def info(self, action, data=None):
        self._event("info", action, data)

    def warn(self, action, data=None):
        self._event("warn", action, data)

    def error(self, action, data=None):
        self.errors += 1
        payload = data if data is not None else {}
        if isinstance(payload, BaseException):
            err = {
                "name": type(payload).__name__,
                "message": str(payload),
            }
            if self.trace:
                err["stack"] = "".join(traceback.format_exception(
                    type(payload), payload, payload.__traceback__))
            payload = err
        self._event("error", action, payload)

    def step(self, action, data=None):
        payload = data if data is not None else {}
        self.steps += 1
        if isinstance(payload, dict):
            tokens = payload.get("tokens")
            if isinstance(tokens, (int, float)) and not isinstance(tokens, bool):
                self.total_tokens += tokens
            duration = payload.get("duration_ms")
            if isinstance(duration, (int, float)) and not isinstance(duration, bool):
                self.total_duration_ms += duration

        if LEVELS["info"] < self.threshold:
            return

        if self.format == "json":
            self._write_line(json.dumps({
                "ts": _iso_from_ms(int(time.time() * 1000)),
                "level": "info",
                "action": str(action),
                "step": self.steps,
                "data": payload,
            }, default=str))
        else:
            self._write_line("{0} [INFO] {1} step={2} {3}".format(
                _iso_from_ms(int(time.time() * 1000)), action, self.steps,
                json.dumps(payload, default=str)))

    def summary(self):
        end = int(time.time() * 1000)
        summary = {
            "total_steps": self.steps,
            "errors": self.errors,
            "total_tokens": self.total_tokens,
            "total_duration_ms": self.total_duration_ms,
            "start_time": self.start_time,
            "end_time": _iso_from_ms(end),
        }
        if self.format == "json":
            self._write_line(json.dumps(summary, default=str))
        else:
            self._write_line(
                "[SUMMARY] steps={0} errors={1} tokens={2} duration_ms={3}".format(
                    summary["total_steps"], summary["errors"],
                    summary["total_tokens"], summary["total_duration_ms"]))
        return summary

    def close(self):
        if self._closed:
            return
        self._closed = True
        if self._own_stream:
            try:
                self.stream.close()
            except Exception:
                pass


def create_logger(output="stdout", format="json", level="info", trace=False):
    return Logger(output=output, format=format, level=level, trace=trace)


def _number(value):
    if isinstance(value, bool):
        return 0
    if isinstance(value, (int, float)):
        return value
    return 0


def summarise(records):
    """Build the run summary from the records of a JSONL log."""
    total_steps = 0
    errors = 0
    total_tokens = 0
    total_duration_ms = 0
    first_ts = None
    last_ts = None
    summary_record = None

    for record in records:
        ts = record.get("ts")
        if isinstance(ts, str):
            if first_ts is None:
                first_ts = ts
            last_ts = ts

        if record.get("level") == "error":
            errors += 1

        if "step" in record:
            total_steps += 1

        data = record.get("data")
        if isinstance(data, dict):
            total_tokens += _number(data.get("tokens"))
            total_duration_ms += _number(data.get("duration_ms"))

        if "total_steps" in record:
            summary_record = record

    if summary_record is not None:
        result = {
            "total_steps": int(_number(summary_record.get("total_steps"))),
            "errors": int(_number(summary_record.get("errors"))),
            "total_tokens": _number(summary_record.get("total_tokens")),
            "total_duration_ms": _number(summary_record.get("total_duration_ms")),
            "start_time": summary_record.get("start_time") or first_ts,
            "end_time": summary_record.get("end_time") or last_ts,
        }
        return result

    return {
        "total_steps": total_steps,
        "errors": errors,
        "total_tokens": total_tokens,
        "total_duration_ms": total_duration_ms,
        "start_time": first_ts,
        "end_time": last_ts,
    }


def parse_args(argv):
    files = []
    as_json = False
    for arg in argv:
        if arg == "--json":
            as_json = True
        elif arg.startswith("-"):
            raise ValueError("unknown option: {0}".format(arg))
        else:
            files.append(arg)
    return files, as_json


def run(argv):
    try:
        files, as_json = parse_args(list(argv))
    except ValueError as exc:
        print("frota log: error: {0}".format(exc), file=sys.stderr)
        print(USAGE, file=sys.stderr)
        return 2

    if len(files) != 1:
        print(USAGE, file=sys.stderr)
        return 2

    path = Path(files[0])
    if not path.exists():
        print("File not found: {0}".format(files[0]), file=sys.stderr)
        return 2
    if not path.is_file():
        print("Not a file: {0}".format(files[0]), file=sys.stderr)
        return 2

    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        print("Cannot read {0}: {1}".format(files[0], exc), file=sys.stderr)
        return 2

    records = []
    skipped = 0
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except ValueError:
            skipped += 1
            continue
        if isinstance(record, dict):
            records.append(record)
        else:
            skipped += 1

    if skipped:
        print("frota log: warning: skipped {0} invalid line(s)".format(skipped),
              file=sys.stderr)

    if not records:
        print("frota log: no valid records in {0}".format(files[0]), file=sys.stderr)
        return 2

    result = summarise(records)
    result["file"] = str(path.absolute())
    result["records"] = len(records)

    if as_json:
        print(json.dumps(result, indent=2))
    else:
        print("frota log")
        print("File: {0}".format(result["file"]))
        print("Records: {0}".format(result["records"]))
        print("Steps: {0}".format(result["total_steps"]))
        print("Errors: {0}".format(result["errors"]))
        print("Tokens: {0}".format(result["total_tokens"]))
        print("Duration: {0} ms".format(result["total_duration_ms"]))
        if result.get("start_time") or result.get("end_time"):
            print("Window: {0} -> {1}".format(
                result.get("start_time"), result.get("end_time")))

    return 0
