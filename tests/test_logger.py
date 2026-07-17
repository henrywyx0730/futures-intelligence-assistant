"""Tests for application logging configuration."""

from contextlib import redirect_stderr
from io import StringIO
import logging
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from futures_intelligence.utils.logger import configure_logging


class LoggingConfigurationTests(unittest.TestCase):
    """Validate console and file logging configuration."""

    def tearDown(self) -> None:
        logger = logging.getLogger("futures_intelligence")
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)
            handler.close()

    def test_writes_configured_level_to_console_and_file(self) -> None:
        with TemporaryDirectory() as directory:
            log_file = Path(directory) / "application.log"
            console = StringIO()

            with redirect_stderr(console):
                logger = configure_logging("DEBUG", log_file)
                logger.debug("logging infrastructure test")

            for handler in logger.handlers:
                handler.flush()

            self.assertEqual(logger.level, logging.DEBUG)
            self.assertIn("logging infrastructure test", console.getvalue())
            self.assertIn("logging infrastructure test", log_file.read_text())

    def test_uses_info_for_invalid_log_level(self) -> None:
        with TemporaryDirectory() as directory:
            logger = configure_logging("invalid", Path(directory) / "application.log")

            self.assertEqual(logger.level, logging.INFO)


if __name__ == "__main__":
    unittest.main()
