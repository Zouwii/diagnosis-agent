from __future__ import annotations

import unittest

from engine.mode_registry import MODE_SPECS, validate_mode_params


class ModeRegistryTests(unittest.TestCase):
    def test_four_modes_map_to_fixed_collection_skills(self) -> None:
        self.assertEqual(
            {mode: spec.collection_skill for mode, spec in MODE_SPECS.items()},
            {
                "internal_robot": "robot-peek",
                "tb_task": "teambition",
                "remote_site": "remote-hand",
                "local_logs": "robot-diagnosis",
            },
        )
        self.assertTrue(all(spec.analysis_skill == "robot-diagnosis" for spec in MODE_SPECS.values()))

    def test_each_mode_requires_its_collection_parameters(self) -> None:
        valid = {
            "internal_robot": {"robot_ip": "172.22.0.2"},
            "tb_task": {"task_url": "https://example.com/task/1"},
            "remote_site": {"frp_port": 22022, "site_robot_ip": "192.168.1.2"},
            "local_logs": {"log_path": "/tenant/robot.log"},
        }
        for mode, params in valid.items():
            with self.subTest(mode=mode):
                self.assertEqual(validate_mode_params(mode, params).mode, mode)
                with self.assertRaises(ValueError):
                    validate_mode_params(mode, {})

    def test_arbitrary_skill_or_auto_mode_is_not_allowed(self) -> None:
        with self.assertRaises(ValueError):
            validate_mode_params("auto", {})
        with self.assertRaises(ValueError):
            validate_mode_params("shell", {})


if __name__ == "__main__":
    unittest.main()
