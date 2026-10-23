"""
Конфигурация для бота Mattermost
"""

import logging
import os
import tempfile
import time
from pathlib import Path
from typing import ClassVar
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

_TRUE_VALUES = {"1", "true", "yes", "on", "y"}
_FALSE_VALUES = {"0", "false", "no", "off", "n"}


def _env_bool(name: str, default: bool = True) -> bool:
    """Разобрать булеву переменную окружения. Нераспознанное значение не отключает проверки безопасности."""
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    value = raw.strip().lower()
    if value in _TRUE_VALUES:
        return True
    if value in _FALSE_VALUES:
        return False
    logger.warning("Некорректное значение %s=%r, используется %s", name, raw, default)
    return default


def _apply_timezone(name: str) -> str:
    """Применить TIMEZONE к процессу: date.today(), datetime.now() и расписание работают в этом поясе"""
    try:
        ZoneInfo(name)
    except Exception:  # ZoneInfoNotFoundError, ValueError, OSError
        logger.warning("Часовой пояс %r не найден (установлен ли tzdata?), используется часовой пояс системы", name)
        return name
    os.environ["TZ"] = name
    if hasattr(time, "tzset"):
        time.tzset()
    return name


def _resolve_writable_file_path(raw_path: str, fallback_filename: str) -> str:
    """Вернуть writable путь; при проблемах перейти в /tmp."""
    path = Path(raw_path)

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8"):
            pass
        return str(path)
    except OSError:
        fallback_dir = Path(tempfile.gettempdir()) / "project_monitor_bot"
        fallback_dir.mkdir(parents=True, exist_ok=True)
        fallback_path = fallback_dir / fallback_filename
        return str(fallback_path)


class Config:
    # Mattermost настройки
    MATTERMOST_URL = os.getenv("MATTERMOST_URL", "https://your-mattermost-server.com")
    MATTERMOST_TOKEN = os.getenv("MATTERMOST_TOKEN")
    MATTERMOST_USERNAME = os.getenv("MATTERMOST_USERNAME", "standup-bot")
    MATTERMOST_TEAM = os.getenv("MATTERMOST_TEAM")  # Команда в Mattermost
    MATTERMOST_CHANNEL_ID = os.getenv("MATTERMOST_CHANNEL_ID")  # ID канала для отчетов
    MATTERMOST_SSL_VERIFY = _env_bool("MATTERMOST_SSL_VERIFY")

    # Jira настройки (on-premise)
    JIRA_URL = os.getenv("JIRA_URL", "https://jira.your-company.com")
    JIRA_VERIFY_SSL = _env_bool("JIRA_VERIFY_SSL")

    # Tempo API настройки (опциональные)
    TEMPO_API_URL = os.getenv("TEMPO_API_URL")
    TEMPO_API_TOKEN = os.getenv("TEMPO_API_TOKEN")

    # База данных
    DATABASE_PATH = _resolve_writable_file_path(os.getenv("DATABASE_PATH", "standup_bot.db"), "standup_bot.db")

    # Администраторы (email адреса, разделенные запятыми)
    ADMIN_EMAILS: ClassVar[list[str]] = [
        email.strip() for email in os.getenv("ADMIN_EMAILS", "").split(",") if email.strip()
    ]

    # Расписание проверки (время в формате HH:MM)
    CHECK_TIME = os.getenv("CHECK_TIME", "12:00")

    # Часовой пояс
    TIMEZONE = _apply_timezone(os.getenv("TIMEZONE", "Europe/Moscow"))

    # API производственного календаря
    CALENDAR_API_URL = os.getenv("CALENDAR_API_URL", "https://calendar.kuzyak.in")

    # Каталог для временных файлов (графики аналитики)
    ARTIFACTS_DIR = os.getenv("ARTIFACTS_DIR", tempfile.gettempdir())

    # Файл-признак живости планировщика (для HEALTHCHECK)
    HEARTBEAT_FILE = str(Path(DATABASE_PATH).parent / ".heartbeat")

    # Логирование
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    LOG_FILE = _resolve_writable_file_path(os.getenv("LOG_FILE", "standup_bot.log"), "standup_bot.log")


config = Config()
