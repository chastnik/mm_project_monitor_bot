import os
import tempfile
import unittest
import importlib
from pathlib import Path
from unittest.mock import patch


class TestPasswordCryptoSaltPath(unittest.TestCase):
    def test_uses_database_directory_when_cwd_is_not_writable(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            readonly_dir = Path(tmp_dir) / "readonly"
            data_dir = Path(tmp_dir) / "data"
            readonly_dir.mkdir()
            data_dir.mkdir()
            readonly_dir.chmod(0o500)

            original_cwd = Path.cwd()
            original_database_path = os.environ.get("DATABASE_PATH")
            original_salt_path = os.environ.get("CRYPTO_SALT_FILE")
            try:
                os.environ["DATABASE_PATH"] = str(data_dir / "standup_bot.db")
                os.environ.pop("CRYPTO_SALT_FILE", None)
                os.chdir(readonly_dir)

                import crypto_utils

                crypto_utils = importlib.reload(crypto_utils)
                crypto = crypto_utils.PasswordCrypto()

                self.assertEqual(len(crypto.salt), 16)
                self.assertTrue((data_dir / ".crypto_salt").exists())
            finally:
                if original_database_path is None:
                    os.environ.pop("DATABASE_PATH", None)
                else:
                    os.environ["DATABASE_PATH"] = original_database_path
                if original_salt_path is None:
                    os.environ.pop("CRYPTO_SALT_FILE", None)
                else:
                    os.environ["CRYPTO_SALT_FILE"] = original_salt_path
                os.chdir(original_cwd)

    def test_falls_back_to_tmp_when_all_project_paths_are_not_writable(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            readonly_dir = Path(tmp_dir) / "readonly"
            readonly_dir.mkdir()
            readonly_dir.chmod(0o500)

            original_cwd = Path.cwd()
            original_database_path = os.environ.get("DATABASE_PATH")
            original_salt_path = os.environ.get("CRYPTO_SALT_FILE")
            try:
                os.environ["DATABASE_PATH"] = "data/standup_bot.db"
                os.environ.pop("CRYPTO_SALT_FILE", None)
                os.chdir(readonly_dir)

                import crypto_utils

                with patch("tempfile.gettempdir", return_value=tmp_dir):
                    crypto_utils = importlib.reload(crypto_utils)
                    crypto = crypto_utils.PasswordCrypto()

                self.assertEqual(len(crypto.salt), 16)
                self.assertTrue((Path(tmp_dir) / "project_monitor_bot" / ".crypto_salt").exists())
            finally:
                if original_database_path is None:
                    os.environ.pop("DATABASE_PATH", None)
                else:
                    os.environ["DATABASE_PATH"] = original_database_path
                if original_salt_path is None:
                    os.environ.pop("CRYPTO_SALT_FILE", None)
                else:
                    os.environ["CRYPTO_SALT_FILE"] = original_salt_path
                os.chdir(original_cwd)
