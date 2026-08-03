from __future__ import annotations

import unittest
from pathlib import Path


class WebUiTests(unittest.TestCase):
    def test_standalone_ui_contains_four_modes_and_case_endpoints(self) -> None:
        page = Path(__file__).resolve().parents[1] / "web" / "index.html"
        text = page.read_text(encoding="utf-8")
        for mode in ("internal_robot", "tb_task", "remote_site", "local_logs"):
            self.assertIn(mode, text)
        self.assertIn("/api/cases/uploads", text)
        self.assertIn("new EventSource", text)
        self.assertIn("/report", text)


if __name__ == "__main__":
    unittest.main()
