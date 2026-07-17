"""Persistent local storage for generated morning briefs."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path


def save_morning_brief(
    brief: str,
    output_directory: str | Path,
    timestamp: datetime | None = None,
) -> Path:
    """Save *brief* as a Markdown file named for its UTC run date."""
    run_time = timestamp or datetime.now(timezone.utc)
    directory = Path(output_directory)
    directory.mkdir(parents=True, exist_ok=True)
    output_path = directory / f"{run_time.date().isoformat()}.md"
    output_path.write_text(brief, encoding="utf-8")
    return output_path
