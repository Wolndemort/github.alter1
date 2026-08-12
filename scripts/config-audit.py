#!/usr/bin/env python3
"""Print a non-secret config audit and fail only on critical warnings."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from config import config
from utils.config_audit import configuration_snapshot


def main() -> int:
    report = configuration_snapshot(config)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    critical = {"no_free_models_configured", "yandex_geocoder_unconfigured"}
    return 1 if critical.intersection(report["warnings"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
