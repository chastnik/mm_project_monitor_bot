"""
Утилиты для шифрования и дешифрования паролей пользователей
"""

import base64
import hashlib
import logging
import os
import tempfile
from pathlib import Path

from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

logger = logging.getLogger(__name__)


class PasswordCrypto:
    def __init__(self):
        self.salt = self._get_or_create_salt()
        self.key = self._derive_key()
        self.cipher = Fernet(self.key)

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
            "Не удалось получить или создать salt файл ни в одном пути: "
            f"{', '.join(str(path) for path in salt_paths)}"
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

    def _derive_key(self) -> bytes:
        """Создать ключ шифрования из соли"""
        # Используем фиксированный пароль + соль для создания ключа
        # В продакшене лучше использовать переменную окружения
        base_password = "MM_STANDUP_BOT_ENCRYPTION_KEY_2024"
        base_password_bytes = base_password.encode()
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

            encrypted_data = self.cipher.encrypt(password.encode("utf-8"))
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
            decrypted_data = self.cipher.decrypt(encrypted_data)
            return decrypted_data.decode("utf-8")

        except Exception as e:
            logger.error(f"Ошибка расшифровки пароля: {e}")
            raise e from None

    def is_encrypted(self, password_data: str) -> bool:
        """Проверить, зашифрован ли пароль"""
        try:
            # Попытаемся расшифровать
            self.decrypt_password(password_data)
            return True
        except Exception:
            return False


# Глобальный экземпляр для использования в приложении
password_crypto = PasswordCrypto()
