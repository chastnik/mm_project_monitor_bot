import base64
import importlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cryptography.fernet import InvalidToken


class TestPasswordCryptoSaltPath(unittest.TestCase):
    def test_uses_database_directory_when_cwd_is_not_writable(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            readonly_dir = Path(tmp_dir) / "readonly"
            data_dir = Path(tmp_dir) / "data"
            readonly_dir.mkdir()
            data_dir.mkdir()
            # ".crypto_salt" в текущем каталоге - каталог, а не файл: использовать его нельзя даже под root
            (readonly_dir / ".crypto_salt").mkdir()

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

    def test_falls_back_to_hashlib_when_sha256_is_unsupported_in_cryptography(self):
        import crypto_utils

        crypto_utils = importlib.reload(crypto_utils)
        fixed_salt = b"\x01" * 16
        fallback_key = b"\x02" * 32

        with (
            patch.object(crypto_utils.PasswordCrypto, "_get_or_create_salt", return_value=fixed_salt),
            patch.object(
                crypto_utils,
                "PBKDF2HMAC",
                side_effect=crypto_utils.UnsupportedAlgorithm("sha256 is not supported for PBKDF2."),
            ),
            patch.object(crypto_utils.hashlib, "pbkdf2_hmac", return_value=fallback_key) as mock_pbkdf2,
        ):
            crypto = crypto_utils.PasswordCrypto()

        self.assertEqual(crypto.key, base64.urlsafe_b64encode(fallback_key))
        mock_pbkdf2.assert_called_once_with(
            "sha256",
            os.environ["ENCRYPTION_KEY"].encode(),
            fixed_salt,
            100000,
            dklen=32,
        )

    def test_falls_back_to_tmp_when_all_project_paths_are_not_writable(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            # Делаем недоступными все пути внутри проекта так, чтобы это работало и под root:
            # "data" - обычный файл (в нем нельзя создать salt), ".crypto_salt" - каталог (его нельзя прочитать)
            readonly_dir = Path(tmp_dir) / "readonly"
            readonly_dir.mkdir()
            (readonly_dir / "data").touch()
            (readonly_dir / ".crypto_salt").mkdir()

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


class TestEncryptionKey(unittest.TestCase):
    def test_missing_key_does_not_break_import_but_blocks_encryption(self):
        import crypto_utils

        with patch.dict(os.environ, {"ENCRYPTION_KEY": ""}):
            crypto = crypto_utils.PasswordCrypto()

        with self.assertRaises(crypto_utils.EncryptionKeyMissingError):
            crypto.encrypt_password("token")

    def test_different_keys_give_different_fingerprints_and_cannot_decrypt(self):
        import crypto_utils

        with patch.dict(os.environ, {"ENCRYPTION_KEY": "first-secret-key-0123456789"}):
            first = crypto_utils.PasswordCrypto()
        with patch.dict(os.environ, {"ENCRYPTION_KEY": "second-secret-key-0123456789"}):
            second = crypto_utils.PasswordCrypto()

        encrypted = first.encrypt_password("token")
        self.assertEqual("token", first.decrypt_password(encrypted))
        self.assertNotEqual(first.key_fingerprint(), second.key_fingerprint())
        with self.assertRaises(InvalidToken):
            second.decrypt_password(encrypted)
