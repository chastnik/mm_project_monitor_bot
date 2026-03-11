import importlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class TestConfigWritablePaths(unittest.TestCase):
    def test_uses_original_paths_when_writable(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            data_dir = Path(tmp_dir) / "data"
            data_dir.mkdir()
            db_path = data_dir / "standup_bot.db"
            log_path = data_dir / "standup_bot.log"

            old_db = os.environ.get("DATABASE_PATH")
            old_log = os.environ.get("LOG_FILE")
            try:
                os.environ["DATABASE_PATH"] = str(db_path)
                os.environ["LOG_FILE"] = str(log_path)

                import config as config_module

                config_module = importlib.reload(config_module)
                self.assertEqual(config_module.config.DATABASE_PATH, str(db_path))
                self.assertEqual(config_module.config.LOG_FILE, str(log_path))
            finally:
                if old_db is None:
                    os.environ.pop("DATABASE_PATH", None)
                else:
                    os.environ["DATABASE_PATH"] = old_db
                if old_log is None:
                    os.environ.pop("LOG_FILE", None)
                else:
                    os.environ["LOG_FILE"] = old_log

    def test_falls_back_to_tmp_when_paths_not_writable(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            readonly_dir = Path(tmp_dir) / "readonly"
            readonly_dir.mkdir()
            readonly_dir.chmod(0o500)

            old_db = os.environ.get("DATABASE_PATH")
            old_log = os.environ.get("LOG_FILE")
            try:
                os.environ["DATABASE_PATH"] = str(readonly_dir / "standup_bot.db")
                os.environ["LOG_FILE"] = str(readonly_dir / "standup_bot.log")

                import config as config_module

                with patch("tempfile.gettempdir", return_value=tmp_dir):
                    config_module = importlib.reload(config_module)

                self.assertEqual(
                    config_module.config.DATABASE_PATH,
                    str(Path(tmp_dir) / "project_monitor_bot" / "standup_bot.db"),
                )
                self.assertEqual(
                    config_module.config.LOG_FILE,
                    str(Path(tmp_dir) / "project_monitor_bot" / "standup_bot.log"),
                )
            finally:
                if old_db is None:
                    os.environ.pop("DATABASE_PATH", None)
                else:
                    os.environ["DATABASE_PATH"] = old_db
                if old_log is None:
                    os.environ.pop("LOG_FILE", None)
                else:
                    os.environ["LOG_FILE"] = old_log
