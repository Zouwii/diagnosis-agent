from __future__ import annotations

import unittest

from agent.graph import graph


class GraphTopologyTests(unittest.TestCase):
    def test_graph_wraps_the_complete_cli_workflow(self) -> None:
        self.assertIn(("__start__", "run_cli_workflow"), graph.edges)
        self.assertIn(("run_cli_workflow", "__end__"), graph.edges)
        self.assertEqual(
            {name for name in graph.nodes if name not in {"__start__", "__end__"}},
            {"run_cli_workflow"},
        )


if __name__ == "__main__":
    unittest.main()
