"""Tests for the scheduler runner abstraction."""

import unittest
from unittest.mock import Mock

from futures_intelligence.scheduler import SchedulerRunner


class SchedulerRunnerTests(unittest.TestCase):
    """Validate scheduler-to-service delegation."""

    def test_runs_morning_brief_service_once(self) -> None:
        service = Mock()
        service.run.return_value = "Morning Futures Brief"

        brief = SchedulerRunner(service).run()

        service.run.assert_called_once_with()
        self.assertEqual(brief, "Morning Futures Brief")


if __name__ == "__main__":
    unittest.main()
