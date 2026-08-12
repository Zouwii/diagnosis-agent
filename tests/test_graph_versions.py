from __future__ import annotations

import unittest

from agent.graph import GRAPHS


class GraphVersionTests(unittest.TestCase):
    def test_origin_v1_does_not_use_the_split_nodes(self) -> None:
        self.assertEqual(
            {name for name in GRAPHS["origin-v1"].nodes if name not in {"__start__", "__end__"}},
            {"diagnosis_cli"},
        )

    def test_graph_v1_has_a_three_stage_shape(self) -> None:
        self.assertEqual(
            {name for name in GRAPHS["graph-v1"].nodes if name not in {"__start__", "__end__"}},
            {"collect", "analyze", "report"},
        )


if __name__ == "__main__":
    unittest.main()
