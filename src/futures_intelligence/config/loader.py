"""Load project configuration and commodity knowledge YAML files."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[3]
CONFIGURATION_FILES = {
    "watchlist": PROJECT_ROOT / "config" / "watchlist.yaml",
    "sources": PROJECT_ROOT / "config" / "sources.yaml",
    "commodity_relationships": PROJECT_ROOT
    / "knowledge"
    / "commodity_relationships.yaml",
}


def load_yaml_file(path: Path) -> dict[str, Any]:
    """Read a YAML mapping from *path*."""
    if not path.is_file():
        raise FileNotFoundError(f"Configuration file not found: {path}")

    with path.open(encoding="utf-8") as file:
        data = yaml.safe_load(file)

    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError(f"Configuration file must contain a YAML mapping: {path}")
    return data


def load_all_configurations() -> dict[str, dict[str, Any]]:
    """Load all configuration files required by the application foundation."""
    return {
        name: load_yaml_file(path)
        for name, path in CONFIGURATION_FILES.items()
    }

