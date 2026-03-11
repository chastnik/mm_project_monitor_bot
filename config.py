"""
Конфигурация для бота Mattermost
"""

import os
import tempfile
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


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
    MATTERMOST_SSL_VERIFY = os.getenv("MATTERMOST_SSL_VERIFY", "true").lower() == "true"

    # Jira настройки (on-premise)
    JIRA_URL = os.getenv("JIRA_URL", "https://jira.your-company.com")
    JIRA_VERIFY_SSL = os.getenv("JIRA_VERIFY_SSL", "true").lower() == "true"

    # Tempo API настройки (опциональные)
    TEMPO_API_URL = os.getenv("TEMPO_API_URL")
    TEMPO_API_TOKEN = os.getenv("TEMPO_API_TOKEN")

    # База данных
    DATABASE_PATH = _resolve_writable_file_path(os.getenv("DATABASE_PATH", "standup_bot.db"), "standup_bot.db")

    # Администраторы (email адреса, разделенные запятыми)
    ADMIN_EMAILS = os.getenv("ADMIN_EMAILS", "").split(",")

    # Расписание проверки (время в формате HH:MM)
    CHECK_TIME = os.getenv("CHECK_TIME", "09:00")

    # Часовой пояс
    TIMEZONE = os.getenv("TIMEZONE", "Europe/Moscow")

    # API производственного календаря
    CALENDAR_API_URL = os.getenv("CALENDAR_API_URL", "https://calendar.kuzyak.in")

    # Логирование
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    LOG_FILE = _resolve_writable_file_path(os.getenv("LOG_FILE", "standup_bot.log"), "standup_bot.log")


config = Config()
