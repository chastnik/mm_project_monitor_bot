"""
Утилиты для шифрования и дешифрования токенов пользователей.

Ключ шифрования выводится из секрета ENCRYPTION_KEY (переменная окружения) и соли из файла .crypto_salt.
Секрет хранится отдельно от базы данных: без него токены из БД расшифровать нельзя.
"""

import base64
import hashlib
import hmac
import logging
import os
import tempfile
from pathlib import Path

from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

logger = logging.getLogger(__name__)

# Минимальная длина секрета ENCRYPTION_KEY
MIN_ENCRYPTION_KEY_LENGTH = 16


class EncryptionKeyMissingError(RuntimeError):
    """Не задан секрет ENCRYPTION_KEY"""


def get_encryption_secret() -> str | None:
    """Секрет для шифрования токенов из переменной окружения ENCRYPTION_KEY"""
    secret = os.getenv("ENCRYPTION_KEY", "").strip()
    return secret or None


class PasswordCrypto:
    def __init__(self):
        self.salt = self._get_or_create_salt()
        self.key = None
        self.cipher = None

        secret = get_encryption_secret()
        if secret:
            self.key = self._derive_key(secret)
            self.cipher = Fernet(self.key)
        else:
            # Не падаем при импорте: main.py проверяет ENCRYPTION_KEY при запуске и сообщает понятную ошибку
            logger.warning("ENCRYPTION_KEY не задан - шифрование токенов недоступно")

    def _require_cipher(self) -> Fernet:
        if self.cipher is None:
            raise EncryptionKeyMissingError("Не задан ENCRYPTION_KEY - шифрование токенов недоступно")
        return self.cipher

    def key_fingerprint(self) -> str:
        """Отпечаток ключа шифрования: позволяет обнаружить смену ключа, не раскрывая сам ключ"""
        self._require_cipher()
        return hmac.new(self.key, b"project-monitor-bot:key-fingerprint", hashlib.sha256).hexdigest()

    def _get_or_create_salt(self) -> bytes:
        """Получить или создать соль для шифрования"""
        salt_paths = self._get_salt_paths()
        last_error = None

        for salt_file in salt_paths:
            try:
                salt_file.parent.mkdir(parents=True, exist_ok=True)

                if salt_file.exists():
                    with salt_file.open("rb") as f:
                        salt = f.read()
                    logger.debug("Соль загружена из файла: %s", salt_file)
                    return salt

                salt = os.urandom(16)  # 16 байт случайной соли
                with salt_file.open("wb") as f:
                    f.write(salt)
                # Устанавливаем безопасные права доступа только для владельца
                os.chmod(salt_file, 0o600)
                logger.info("Создана новая соль для шифрования: %s", salt_file)
                return salt
            except OSError as exc:
                last_error = exc
                logger.warning("Не удалось использовать salt файл %s: %s", salt_file, exc)

        raise RuntimeError(
            f"Не удалось получить или создать salt файл ни в одном пути: {', '.join(str(path) for path in salt_paths)}"
        ) from last_error

    def _get_salt_paths(self) -> list[Path]:
        """Список путей для salt в порядке приоритета."""
        candidates: list[Path] = []

        env_path = os.getenv("CRYPTO_SALT_FILE")
        if env_path:
            candidates.append(Path(env_path))

        database_path = os.getenv("DATABASE_PATH", "data/standup_bot.db")
        db_dir = Path(database_path).parent
        candidates.extend(
            [
                db_dir / ".crypto_salt",
                Path("data/.crypto_salt"),
                Path(".crypto_salt"),
                Path(tempfile.gettempdir()) / "project_monitor_bot" / ".crypto_salt",
            ]
        )

        # Удаляем дубликаты путей, сохраняя порядок приоритета.
        unique_candidates: list[Path] = []
        seen: set[Path] = set()
        for path in candidates:
            if path in seen:
                continue
            unique_candidates.append(path)
            seen.add(path)
        return unique_candidates

    def _derive_key(self, secret: str) -> bytes:
        """Создать ключ шифрования из секрета ENCRYPTION_KEY и соли"""
        base_password_bytes = secret.encode()
        iterations = 100000

        try:
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=self.salt,
                iterations=iterations,  # Много итераций для безопасности
            )
            return base64.urlsafe_b64encode(kdf.derive(base_password_bytes))
        except UnsupportedAlgorithm as exc:
            logger.warning(
                "PBKDF2HMAC с SHA256 недоступен в backend cryptography, используем hashlib fallback: %s",
                exc,
            )
            try:
                derived_key = hashlib.pbkdf2_hmac(
                    "sha256",
                    base_password_bytes,
                    self.salt,
                    iterations,
                    dklen=32,
                )
            except ValueError:
                # В крайне ограниченных окружениях sha256 может быть недоступен и в hashlib.
                derived_key = hashlib.pbkdf2_hmac(
                    "sha512",
                    base_password_bytes,
                    self.salt,
                    iterations,
                    dklen=32,
                )
            return base64.urlsafe_b64encode(derived_key)

    def encrypt_password(self, password: str) -> str:
        """Зашифровать пароль"""
        try:
            if not password:
                return ""

            encrypted_data = self._require_cipher().encrypt(password.encode("utf-8"))
            # Кодируем в base64 для хранения в БД
            return base64.urlsafe_b64encode(encrypted_data).decode("utf-8")

        except Exception as e:
            logger.error(f"Ошибка шифрования пароля: {e}")
            raise e from None

    def decrypt_password(self, encrypted_password: str) -> str:
        """Расшифровать пароль"""
        try:
            if not encrypted_password:
                return ""

            # Декодируем из base64
            encrypted_data = base64.urlsafe_b64decode(encrypted_password.encode("utf-8"))
            decrypted_data = self._require_cipher().decrypt(encrypted_data)
            return decrypted_data.decode("utf-8")

        except Exception as e:
            logger.error(f"Ошибка расшифровки пароля: {e}")
            raise e from None


# Глобальный экземпляр для использования в приложении
password_crypto = PasswordCrypto()
