#!/usr/bin/env python3
"""Public-package regression tests for demand-driven asset selection."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


PACKAGE_PARENT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = (
    PACKAGE_PARENT
    if (PACKAGE_PARENT / "scripts/resolve_asset_demand.py").is_file()
    else PACKAGE_PARENT.parent
)
sys.path.insert(0, str(WORKSPACE_ROOT / "scripts"))

from resolve_asset_demand import resolve_asset_demand  # noqa: E402


class AssetDemandResolverTests(unittest.TestCase):
    def test_episode_important_selects_only_consumed_view(self) -> None:
        result = resolve_asset_demand(
            {
                "schema_version": "1.0",
                "project_id": "fixture",
                "demands": [
                    {
                        "demand_id": "DEM-HERO",
                        "shot_ids": ["SH001"],
                        "category": "character",
                        "risk_level": "high",
                        "required": True,
                    }
                ],
                "candidates": [
                    {
                        "asset_id": "CH001-FRONT",
                        "category": "character",
                        "covers": ["DEM-HERO"],
                        "generation_wave": 0,
                        "tier": "episode_important",
                        "angle_pack_mode": "on_demand",
                    },
                    {
                        "asset_id": "CH001-BACK",
                        "category": "character",
                        "covers": [],
                        "generation_wave": 0,
                        "tier": "episode_important",
                        "angle_pack_mode": "on_demand",
                    },
                ],
            },
            registry={},
        )
        selected = result["asset_demand_manifest"]["generation_requirements"]
        self.assertEqual([row["asset_id"] for row in selected], ["CH001-FRONT"])
        self.assertTrue(result["asset_demand_gate"]["passed"])

    def test_series_library_full_pack_is_explicit(self) -> None:
        result = resolve_asset_demand(
            {
                "schema_version": "1.0",
                "project_id": "fixture",
                "policy": {"full_pack_tiers": ["series_core"]},
                "demands": [
                    {
                        "demand_id": "DEM-HERO",
                        "shot_ids": ["SH001"],
                        "category": "character",
                        "risk_level": "high",
                        "required": True,
                    }
                ],
                "candidates": [
                    {
                        "asset_id": "CH001-FRONT",
                        "category": "character",
                        "covers": ["DEM-HERO"],
                        "generation_wave": 0,
                        "tier": "series_core",
                        "angle_pack_mode": "full",
                        "angle_pack_id": "PACK-CH001",
                        "series_library": True,
                    },
                    {
                        "asset_id": "CH001-BACK",
                        "category": "character",
                        "covers": [],
                        "generation_wave": 0,
                        "tier": "series_core",
                        "angle_pack_mode": "full",
                        "angle_pack_id": "PACK-CH001",
                        "series_library": True,
                    },
                ],
            },
            registry={},
        )
        selected = result["asset_demand_manifest"]["generation_requirements"]
        self.assertEqual(
            [row["asset_id"] for row in selected],
            ["CH001-FRONT", "CH001-BACK"],
        )


if __name__ == "__main__":
    unittest.main()
