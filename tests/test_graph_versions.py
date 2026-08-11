from __future__ import annotations

import unittest

from agent.graph import GRAPHS


class GraphVersionTests(unittest.TestCase):
    def test_origin_v1_does_not_use_the_split_nodes(self) -> None:
        self.assertEqual(
            {name for name in GRAPHS["origin-v1"].nodes if name not in {"__start__", "__end__"}},
            {"diagnosis_cli"},
        )

    def test_split_versions_keep_their_three_stage_shape(self) -> None:
        for version in ("origin-split", "graph-v1"):
            self.assertEqual(
                {name for name in GRAPHS[version].nodes if name not in {"__start__", "__end__"}},
                {"collect", "analyze", "report"},
            )


if __name__ == "__main__":
    unittest.main()
