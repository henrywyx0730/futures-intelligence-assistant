"""Tests for local application health reports."""

from datetime import datetime, timezone
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from futures_intelligence.utils.health import write_health_report


class HealthReportTests(unittest.TestCase):
    """Validate health-report persistence."""

    def test_writes_successful_run_report_to_json(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "data" / "health_report.json"
            report = write_health_report(
                path,
                collected_information_count=3,
                generated_analysis_count=2,
                generated_brief_path="data/briefs/2026-07-17.md",
                timestamp=datetime(2026, 7, 17, tzinfo=timezone.utc),
            )

            self.assertEqual(report.execution_status, "success")
            self.assertEqual(report.brief_generation_status, "success")
            self.assertEqual(report.collected_information_count, 3)
            self.assertEqual(report.generated_analysis_count, 2)
            self.assertEqual(report.generated_brief_path, "data/briefs/2026-07-17.md")
            self.assertEqual(
                json.loads(path.read_text()),
                {
                    "last_run_timestamp": "2026-07-17T00:00:00+00:00",
                    "execution_status": "success",
                    "collected_information_count": 3,
                    "generated_analysis_count": 2,
                    "brief_generation_status": "success",
                    "generated_brief_path": "data/briefs/2026-07-17.md",
                },
            )

    def test_writes_failure_status_without_generated_brief(self) -> None:
        with TemporaryDirectory() as directory:
            report = write_health_report(
                Path(directory) / "health_report.json",
                collected_information_count=0,
                generated_analysis_count=0,
                execution_status="failure",
            )

            self.assertEqual(report.execution_status, "failure")
            self.assertEqual(report.brief_generation_status, "not_generated")
            self.assertIsNone(report.generated_brief_path)


if __name__ == "__main__":
    unittest.main()
