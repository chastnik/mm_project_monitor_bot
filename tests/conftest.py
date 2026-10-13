import os

# Секрет для шифрования токенов в тестах (в рабочем окружении задается в .env)
os.environ.setdefault("ENCRYPTION_KEY", "unit-tests-encryption-key-not-for-production")
