from __future__ import annotations

import stat
import tempfile
import textwrap
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace

from server.claude_origin import ClaudeOriginConfig, ClaudeOriginRunner


def make_request(**overrides):
    values = {
        "mode": "local_logs",
        "symptom": "导航失败",
        "log_path": "",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def make_case(case_dir: Path) -> dict:
    return {
        "case_id": "case-claude-test",
        "case_dir": str(case_dir),
        "source_type": "local_logs",
        "mode": "local_logs",
        "extra_params": {"time_window": "", "knowledge_sources": [], "code_sources": []},
    }


def executable_script(directory: Path, body: str) -> Path:
    path = directory / "fake-claude"
    path.write_text("#!/bin/sh\nset -eu\n" + textwrap.dedent(body), encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


class ClaudeOriginRunnerTests(unittest.TestCase):
    def test_command_is_non_interactive_and_budget_is_optional(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            case = make_case(root / "case-claude-test")
            runner = ClaudeOriginRunner(
                case["case_id"],
                case,
                make_request(),
                config=ClaudeOriginConfig(
                    claude_bin="claude",
                    skills_root=root / "skills",
                    model="model-x",
                    max_budget_usd="2.50",
                    timeout_seconds=30,
                ),
            )
            command = runner.build_command("fixed prompt", root / "workspace")
            self.assertEqual(command[:3], ["claude", "-p", "fixed prompt"])
            self.assertIn("stream-json", command)
            self.assertIn("--verbose", command)
            self.assertIn("--include-partial-messages", command)
            self.assertIn("--add-dir", command)
            self.assertIn("--max-budget-usd", command)
            self.assertNotIn("shell", command)
            uuid.UUID(runner.session_id)

    def test_success_persists_stream_and_requires_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            case_dir = root / "case-claude-test"
            (case_dir / "raw").mkdir(parents=True)
            (case_dir / "raw" / "input.log").write_text("ERROR navigation failed\n", encoding="utf-8")
            fake = executable_script(
                root,
                """
                printf '%s\\n' '{\"type\":\"assistant\",\"message\":\"reading raw\"}'
                printf '# report\\nEvidence only\\n' > ../report.md
                """,
            )
            result = ClaudeOriginRunner(
                "case-claude-test",
                make_case(case_dir),
                make_request(),
                config=ClaudeOriginConfig(claude_bin=str(fake), skills_root=root, timeout_seconds=5),
            ).run()
            self.assertTrue(result.ok)
            self.assertTrue((case_dir / "report.md").is_file())
            self.assertIn("stream-json", (case_dir / "claude.command.json").read_text(encoding="utf-8"))
            self.assertIn("reading raw", (case_dir / "claude.stdout.jsonl").read_text(encoding="utf-8"))
            self.assertTrue((case_dir / "events.jsonl").is_file())

    def test_empty_raw_still_starts_claude_and_exposes_case_input(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            case_dir = root / "case-claude-test"
            fake = executable_script(
                root,
                """
                test -s diagnosis.input.json
                test -f CLAUDE.md
                printf '%s\\n' '{\"type\":\"assistant\",\"message\":\"orchestrator started\"}'
                printf '# report\\nInsufficient material\\n' > ../report.md
                """,
            )
            result = ClaudeOriginRunner(
                "case-claude-test",
                make_case(case_dir),
                make_request(mode="tb_task", task_url="https://tb.example/task/1"),
                config=ClaudeOriginConfig(claude_bin=str(fake), skills_root=root, timeout_seconds=5),
            ).run()
            self.assertTrue(result.ok)
            self.assertEqual(result.collection["artifacts"], [])
            self.assertTrue((case_dir / "claude.collection.json").is_file())
            self.assertIn("tb.example/task/1", (case_dir / "claude-workspace" / "diagnosis.input.json").read_text(encoding="utf-8"))
            self.assertIn("diagnosis-orchestrator", (case_dir / "claude-workspace" / "CLAUDE.md").read_text(encoding="utf-8"))

    def test_zero_exit_without_report_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            case_dir = root / "case-claude-test"
            (case_dir / "raw").mkdir(parents=True)
            (case_dir / "raw" / "input.log").write_text("input\n", encoding="utf-8")
            fake = executable_script(root, "printf '%s\\n' '{\"type\":\"result\"}'\n")
            result = ClaudeOriginRunner(
                "case-claude-test",
                make_case(case_dir),
                make_request(),
                config=ClaudeOriginConfig(claude_bin=str(fake), skills_root=root, timeout_seconds=5),
            ).run()
            self.assertFalse(result.ok)
            self.assertIn("report.md", result.error)
            self.assertTrue((case_dir / "claude.error.log").is_file())

    def test_timeout_fails_and_records_exit_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            case_dir = root / "case-claude-test"
            (case_dir / "raw").mkdir(parents=True)
            (case_dir / "raw" / "input.log").write_text("input\n", encoding="utf-8")
            fake = executable_script(root, "sleep 3\n")
            result = ClaudeOriginRunner(
                "case-claude-test",
                make_case(case_dir),
                make_request(),
                config=ClaudeOriginConfig(claude_bin=str(fake), skills_root=root, timeout_seconds=1),
            ).run()
            self.assertFalse(result.ok)
            self.assertIn("超时", result.error)
            self.assertTrue(result.timed_out)
            self.assertTrue((case_dir / "claude.exit.json").is_file() or (case_dir / "claude.error.log").is_file())


if __name__ == "__main__":
    unittest.main()
