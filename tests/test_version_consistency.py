from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from agent.graph import GRAPHS


def _normalized(value: Any, root: Path) -> Any:
    if isinstance(value, dict):
        return {
            key: _normalized(item, root)
            for key, item in sorted(value.items())
            if key not in {"created_at", "updated_at", "collected_at"}
        }
    if isinstance(value, list):
        return [_normalized(item, root) for item in value]
    if isinstance(value, str):
        return value.replace(str(root), "<CASE_ROOT>")
    return value


class VersionConsistencyTests(unittest.IsolatedAsyncioTestCase):
    async def test_origin_and_split_have_equivalent_local_case_results(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            results: dict[str, tuple[dict[str, Any], Path]] = {}
            for version in ("origin-v1", "origin-split"):
                root = base / version
                uploads = root / "uploads"
                uploads.mkdir(parents=True)
                source = uploads / "nav-manager.log"
                source.write_text(
                    "2026-08-03 10:00:00 ERROR error_code: 614028 camera missed\n",
                    encoding="utf-8",
                )
                case_dir = root / "cases" / "same-case"
                state = {
                    "case_id": "same-case",
                    "case_dir": str(case_dir),
                    "input_roots": [str(uploads)],
                    "source_type": "local_logs",
                    "selected_skill": "robot-diagnosis",
                    "symptom": "机器人二维码识别异常，错误码614028",
                    "time_window": "2026-08-03 10:00:00",
                    "extra_params": {
                        "log_path": str(source),
                        "external_evidence": False,
                    },
                    "findings": [],
                    "errors": [],
                    "fallback_triggered": [],
                }
                result = await GRAPHS[version].ainvoke(
                    state,
                    {"configurable": {"thread_id": f"{version}-same-case"}},
                )
                results[version] = (result, case_dir)

            origin_result, origin_dir = results["origin-v1"]
            split_result, split_dir = results["origin-split"]
            self.assertEqual(
                _normalized(origin_result, origin_dir.parents[1]),
                _normalized(split_result, split_dir.parents[1]),
            )

            for filename in (
                "context.json",
                "status.json",
                "collection.json",
                "report.md",
                "human-handoff.md",
                "knowledge-draft.md",
                "next-prompt.md",
            ):
                origin_path = origin_dir / filename
                split_path = split_dir / filename
                self.assertTrue(origin_path.is_file(), filename)
                self.assertTrue(split_path.is_file(), filename)
                if origin_path.suffix == ".json":
                    origin_value = json.loads(origin_path.read_text(encoding="utf-8"))
                    split_value = json.loads(split_path.read_text(encoding="utf-8"))
                else:
                    origin_value = origin_path.read_text(encoding="utf-8")
                    split_value = split_path.read_text(encoding="utf-8")
                self.assertEqual(
                    _normalized(origin_value, origin_dir.parents[1]),
                    _normalized(split_value, split_dir.parents[1]),
                    filename,
                )


if __name__ == "__main__":
    unittest.main()
