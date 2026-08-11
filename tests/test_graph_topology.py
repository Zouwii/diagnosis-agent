from __future__ import annotations

import unittest

from agent.graph import GRAPHS


class GraphTopologyTests(unittest.TestCase):
    def test_origin_v1_is_a_single_complete_diagnosis_cli_node(self) -> None:
        graph = GRAPHS["origin-v1"]
        edges = {(edge.source, edge.target) for edge in graph.get_graph().edges}
        self.assertIn(("__start__", "diagnosis_cli"), edges)
        self.assertIn(("diagnosis_cli", "__end__"), edges)
        self.assertEqual(
            {name for name in graph.nodes if name not in {"__start__", "__end__"}},
            {"diagnosis_cli"},
        )

    def test_all_public_graph_versions_are_registered(self) -> None:
        self.assertEqual(set(GRAPHS), {"origin-v1", "origin-split", "graph-v1"})


if __name__ == "__main__":
    unittest.main()
