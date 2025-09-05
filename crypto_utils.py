"""
Утилиты для шифрования и дешифрования паролей пользователей
"""
import os
import base64
import hashlib
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import logging

logger = logging.getLogger(__name__)

class PasswordCrypto:
    def __init__(self):
        self.salt = self._get_or_create_salt()
        self.key = self._derive_key()
        self.cipher = Fernet(self.key)
    
    def _get_or_create_salt(self) -> bytes:
        """Получить или создать соль для шифрования"""
        salt_file = '.crypto_salt'
        
        if os.path.exists(salt_file):
            with open(salt_file, 'rb') as f:
                salt = f.read()
            logger.debug("Соль загружена из файла")
        else:
            salt = os.urandom(16)  # 16 байт случайной соли
            with open(salt_file, 'wb') as f:
                f.write(salt)
            # Устанавливаем безопасные права доступа только для владельца
            os.chmod(salt_file, 0o600)
            logger.info("Создана новая соль для шифрования")
        
        return salt
    
    def _derive_key(self) -> bytes:
        """Создать ключ шифрования из соли"""
        # Используем фиксированный пароль + соль для создания ключа
        # В продакшене лучше использовать переменную окружения
        base_password = "MM_STANDUP_BOT_ENCRYPTION_KEY_2024"
        
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=self.salt,
            iterations=100000,  # Много итераций для безопасности
        )
        key = base64.urlsafe_b64encode(kdf.derive(base_password.encode()))
        return key
    
    def encrypt_password(self, password: str) -> str:
        """Зашифровать пароль"""
        try:
            if not password:
                return ""
            
            encrypted_data = self.cipher.encrypt(password.encode('utf-8'))
            # Кодируем в base64 для хранения в БД
            return base64.urlsafe_b64encode(encrypted_data).decode('utf-8')
        
        except Exception as e:
            logger.error(f"Ошибка шифрования пароля: {e}")
            raise
    
    def decrypt_password(self, encrypted_password: str) -> str:
        """Расшифровать пароль"""
        try:
            if not encrypted_password:
                return ""
            
            # Декодируем из base64
            encrypted_data = base64.urlsafe_b64decode(encrypted_password.encode('utf-8'))
            decrypted_data = self.cipher.decrypt(encrypted_data)
            return decrypted_data.decode('utf-8')
        
        except Exception as e:
            logger.error(f"Ошибка расшифровки пароля: {e}")
            raise
    
    def is_encrypted(self, password_data: str) -> bool:
        """Проверить, зашифрован ли пароль"""
        try:
            # Попытаемся расшифровать
            self.decrypt_password(password_data)
            return True
        except:
            return False

# Глобальный экземпляр для использования в приложении
password_crypto = PasswordCrypto()

