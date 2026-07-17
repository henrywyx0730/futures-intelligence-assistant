"""Tests for persistent morning brief storage."""

from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from futures_intelligence.utils.brief_storage import save_morning_brief


class MorningBriefStorageTests(unittest.TestCase):
    """Validate Markdown storage for generated briefs."""

    def test_saves_brief_using_utc_run_date_filename(self) -> None:
        with TemporaryDirectory() as directory:
            output_directory = Path(directory) / "nested" / "briefs"

            output_path = save_morning_brief(
                "Morning Futures Brief\n",
                output_directory,
                timestamp=datetime(2026, 7, 17, 8, tzinfo=timezone.utc),
            )

            self.assertEqual(output_path, output_directory / "2026-07-17.md")
            self.assertTrue(output_path.is_file())
            self.assertEqual(output_path.read_text(), "Morning Futures Brief\n")


if __name__ == "__main__":
    unittest.main()
