#!/usr/bin/env python3
"""Dependency-free checks for the packaged demand-driven workflow contract."""

from __future__ import annotations

import unittest
from pathlib import Path


PACKAGE_PARENT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = (
    PACKAGE_PARENT
    if (PACKAGE_PARENT / "drama-workflow.yaml").is_file()
    else PACKAGE_PARENT.parent
)


class AssetDemandWorkflowContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workflow = (WORKSPACE_ROOT / "drama-workflow.yaml").read_text(encoding="utf-8")
        cls.skill_map = (WORKSPACE_ROOT / "drama-skill-map.yaml").read_text(encoding="utf-8")

    def test_demand_stage_precedes_asset_dispatch(self) -> None:
        demand = self.workflow.index("stage_28_asset_demand_resolution:")
        dispatch = self.workflow.index("stage_35_base_asset_dispatch:")
        self.assertLess(demand, dispatch)

    def test_demand_runner_and_gate_are_declared(self) -> None:
        self.assertIn("runner: scripts/resolve_asset_demand.py", self.workflow)
        self.assertIn("gates/asset_demand_coverage_gate.json", self.workflow)
        self.assertTrue((WORKSPACE_ROOT / "scripts/resolve_asset_demand.py").is_file())

    def test_episode_important_defaults_to_on_demand(self) -> None:
        self.assertIn("episode_important: on_demand", self.workflow)
        self.assertIn("skill: [deepwhite-asset-demand-resolver]", self.skill_map)


if __name__ == "__main__":
    unittest.main()
