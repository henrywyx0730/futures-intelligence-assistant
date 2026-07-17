"""Local application health-report persistence."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path


@dataclass(frozen=True)
class HealthReport:
    """A persisted status summary for a morning brief run."""

    last_run_timestamp: str
    execution_status: str
    collected_information_count: int
    generated_analysis_count: int
    brief_generation_status: str
    generated_brief_path: str | None = None

    def to_dict(self) -> dict[str, str | int | None]:
        """Return a JSON-serializable representation of the report."""
        return asdict(self)


def write_health_report(
    path: str | Path,
    collected_information_count: int,
    generated_analysis_count: int,
    generated_brief_path: str | Path | None = None,
    execution_status: str = "success",
    timestamp: datetime | None = None,
) -> HealthReport:
    """Write and return a local health report for an application run."""
    if execution_status not in {"success", "failure"}:
        raise ValueError("execution_status must be 'success' or 'failure'")

    report = HealthReport(
        last_run_timestamp=(timestamp or datetime.now(timezone.utc)).isoformat(),
        execution_status=execution_status,
        collected_information_count=collected_information_count,
        generated_analysis_count=generated_analysis_count,
        brief_generation_status=(
            "success" if execution_status == "success" else "not_generated"
        ),
        generated_brief_path=(
            str(generated_brief_path) if generated_brief_path is not None else None
        ),
    )
    report_path = Path(path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report.to_dict(), indent=2) + "\n",
        encoding="utf-8",
    )
    return report
