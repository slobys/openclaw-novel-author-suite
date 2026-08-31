#!/usr/bin/env python3
"""Display the effective zero-config defaults for debugging."""
from pathlib import Path
import json
base = Path(__file__).resolve().parent.parent
profile = json.loads((base / "assets" / "default-profile.json").read_text(encoding="utf-8"))
print(json.dumps(profile, ensure_ascii=False, indent=2))
