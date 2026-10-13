#!/bin/bash
#
# Добавляет в .env случайный ENCRYPTION_KEY (секрет для шифрования токенов Jira), если его там нет.
# Существующий ключ не меняется: смена ключа сбрасывает сохраненные токены пользователей.
#
# Использование: ./deploy/ensure_encryption_key.sh <путь к .env>
#

set -euo pipefail

ENV_FILE="${1:?Укажите путь к .env}"

if [ ! -f "$ENV_FILE" ]; then
    echo "Файл $ENV_FILE не найден" >&2
    exit 1
fi

if grep -Eq '^[[:space:]]*ENCRYPTION_KEY=[^[:space:]]+' "$ENV_FILE"; then
    exit 0
fi

if command -v openssl >/dev/null 2>&1; then
    NEW_KEY="$(openssl rand -base64 32)"
else
    NEW_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
fi

# Убираем пустую строку ENCRYPTION_KEY= из шаблона, если она есть
sed -i '/^[[:space:]]*ENCRYPTION_KEY=[[:space:]]*$/d' "$ENV_FILE"
[ -n "$(tail -c1 "$ENV_FILE")" ] && echo >> "$ENV_FILE"
{
    echo "# Секрет для шифрования токенов Jira (сгенерирован автоматически). Не меняйте и не теряйте:"
    echo "# при смене ключа пользователям придется заново войти в Jira"
    echo "ENCRYPTION_KEY=$NEW_KEY"
} >> "$ENV_FILE"

echo "В $ENV_FILE добавлен новый ENCRYPTION_KEY"
