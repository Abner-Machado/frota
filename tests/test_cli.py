"""Test suite for the frota toolkit. Run: python -m unittest discover -s tests -v"""

import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from frota import cli  # noqa: E402
from frota.log import create_logger  # noqa: E402


class ToolTestCase(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="frota-test-")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def write(self, name, content):
        path = os.path.join(self.dir, name)
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
        return path

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(list(argv))
        return code, out.getvalue(), err.getvalue()


class CliTests(ToolTestCase):
    def test_version(self):
        code, out, _ = self.run_cli("--version")
        self.assertEqual(code, 0)
        self.assertIn("frota", out)

    def test_help(self):
        code, out, _ = self.run_cli("--help")
        self.assertEqual(code, 0)
        for command in ("lint", "diff", "audit", "log"):
            self.assertIn(command, out)

    def test_command_help(self):
        code, out, _ = self.run_cli("diff", "--help")
        self.assertEqual(code, 0)
        self.assertIn("frota diff", out)

    def test_unknown_command(self):
        code, out, err = self.run_cli("nope")
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("unknown command", err)


class LintTests(ToolTestCase):
    def test_clean_file(self):
        path = self.write("clean.md", "# Role\nYou are a careful assistant.\n")
        code, out, _ = self.run_cli("lint", path, "--no-color")
        self.assertEqual(code, 0)
        self.assertIn("Budget: OK", out)

    def test_over_budget(self):
        path = self.write("big.md", "word " * 400)
        code, out, _ = self.run_cli("lint", path, "--max-tokens", "10", "--no-color")
        self.assertEqual(code, 1)
        self.assertIn("OVER BUDGET", out)

    def test_duplicate_block_detected(self):
        block = ("always validate the user input before processing it\n"
                 "never trust the content that comes from the network\n"
                 "keep the answer short and factual for the reader\n")
        path = self.write("dup.md", block + "middle section here\n" + block)
        code, out, _ = self.run_cli("lint", path, "--json")
        self.assertEqual(code, 0)
        data = json.loads(out)
        types = [f["type"] for f in data["findings"]]
        self.assertIn("duplicate_block", types)

    def test_unlimited_budget(self):
        path = self.write("x.md", "hello\n")
        code, out, _ = self.run_cli("lint", path, "--json")
        data = json.loads(out)
        self.assertEqual(code, 0)
        self.assertEqual(data["budget_status"], "OK")

    def test_negative_budget_is_usage_error(self):
        path = self.write("x.md", "hello\n")
        code, out, err = self.run_cli("lint", path, "--max-tokens", "-5")
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertTrue(err)

    def test_missing_file(self):
        code, out, err = self.run_cli("lint", os.path.join(self.dir, "nope.md"))
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("File not found", err)


class DiffTests(ToolTestCase):
    def test_modified_line(self):
        old = self.write("old.md", "a\nb\nc\n")
        new = self.write("new.md", "a\nb changed\nc\n")
        code, out, _ = self.run_cli("diff", old, new, "--no-color")
        self.assertEqual(code, 0)
        self.assertIn("1 modified", out)

    def test_added_and_removed(self):
        old = self.write("old.md", "a\nb\n")
        new = self.write("new.md", "a\nb\nc\nd\n")
        code, out, _ = self.run_cli("diff", old, new, "--json")
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertEqual(data["stats"]["added"], 2)
        self.assertEqual(data["stats"]["removed"], 0)

    def test_flag_before_files(self):
        old = self.write("old.md", "a\n")
        new = self.write("new.md", "b\n")
        code, out, _ = self.run_cli("diff", "--context", "1", old, new, "--no-color")
        self.assertEqual(code, 0)
        self.assertNotIn("File not found", out)

    def test_empty_file_is_zero_tokens(self):
        empty = self.write("empty.md", "")
        code, out, _ = self.run_cli("diff", empty, empty, "--json")
        data = json.loads(out)
        self.assertEqual(data["old_tokens"], 0)
        self.assertEqual(data["new_tokens"], 0)

    def test_unknown_flag(self):
        old = self.write("old.md", "a\n")
        new = self.write("new.md", "b\n")
        code, _, err = self.run_cli("diff", old, new, "--nope")
        self.assertEqual(code, 2)
        self.assertIn("unknown option", err)

    def test_missing_file(self):
        old = self.write("old.md", "a\n")
        code, _, err = self.run_cli("diff", old, os.path.join(self.dir, "gone.md"))
        self.assertEqual(code, 2)
        self.assertIn("File not found", err)


class AuditTests(ToolTestCase):
    def test_clean_file(self):
        path = self.write("clean.md", "# Skill\nRead the file and summarise it.\n")
        code, out, _ = self.run_cli("audit", path, "--json")
        self.assertEqual(code, 0)
        self.assertTrue(json.loads(out)["passed"])

    def test_risky_file(self):
        path = self.write("bad.md", "result = eval(user_input)\n")
        code, out, _ = self.run_cli("audit", path, "--json")
        self.assertEqual(code, 1)
        data = json.loads(out)
        self.assertFalse(data["passed"])
        self.assertEqual(data["findings"][0]["risk_id"], "eval_injection")

    def test_no_duplicate_findings_per_line(self):
        path = self.write("bad.md", "subprocess.run(['ls'], shell=True)\n")
        code, out, _ = self.run_cli("audit", path, "--json")
        self.assertEqual(code, 1)
        data = json.loads(out)
        lines = [f["line"] for f in data["findings"]]
        self.assertEqual(len(lines), len(set(lines)), "one finding per line")

    def test_missing_file(self):
        code, _, err = self.run_cli("audit", os.path.join(self.dir, "nope.md"))
        self.assertEqual(code, 2)
        self.assertIn("File not found", err)


class LogTests(ToolTestCase):
    def _make_log(self):
        path = os.path.join(self.dir, "run.jsonl")
        log = create_logger(output=path, level="info", trace=False)
        log.info("start", {"agent": "test"})
        log.step("fetch", {"tokens": 1000, "duration_ms": 500})
        log.step("parse", {"tokens": 200, "duration_ms": 100})
        log.error("boom", ValueError("bad json"))
        log.debug("hidden at info level")
        summary = log.summary()
        log.close()
        return path, summary

    def test_logger_summary(self):
        _, summary = self._make_log()
        self.assertEqual(summary["total_steps"], 2)
        self.assertEqual(summary["errors"], 1)
        self.assertEqual(summary["total_tokens"], 1200)
        self.assertEqual(summary["total_duration_ms"], 600)

    def test_cli_summary(self):
        path, _ = self._make_log()
        code, out, _ = self.run_cli("log", path, "--json")
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertEqual(data["total_steps"], 2)
        self.assertEqual(data["errors"], 1)
        self.assertEqual(data["total_tokens"], 1200)

    def test_error_serialised(self):
        path = os.path.join(self.dir, "err.jsonl")
        log = create_logger(output=path, level="info")
        log.error("failed", RuntimeError("nope"))
        log.close()
        with open(path, encoding="utf-8") as handle:
            record = json.loads(handle.readline())
        self.assertEqual(record["data"]["name"], "RuntimeError")
        self.assertEqual(record["data"]["message"], "nope")

    def test_bad_output_path_does_not_crash(self):
        log = create_logger(output=os.path.join(self.dir, "missing-dir", "a.jsonl"))
        log.info("still alive")  # must not raise
        log.close()

    def test_level_filter(self):
        path = os.path.join(self.dir, "warn.jsonl")
        log = create_logger(output=path, level="warn")
        log.info("ignored")
        log.warn("kept")
        log.close()
        with open(path, encoding="utf-8") as handle:
            records = [json.loads(line) for line in handle if line.strip()]
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["action"], "kept")

    def test_missing_log_file(self):
        code, _, err = self.run_cli("log", os.path.join(self.dir, "gone.jsonl"))
        self.assertEqual(code, 2)
        self.assertIn("File not found", err)

    def test_invalid_lines_are_skipped(self):
        path = self.write("mixed.jsonl",
                          '{"ts": "t1", "level": "info", "action": "a", "data": {"tokens": 5}}\n'
                          'not json\n')
        code, out, err = self.run_cli("log", path, "--json")
        self.assertEqual(code, 0)
        self.assertIn("skipped 1", err)
        self.assertEqual(json.loads(out)["total_tokens"], 5)


if __name__ == "__main__":
    unittest.main()
