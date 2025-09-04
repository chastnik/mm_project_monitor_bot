"""
Конфигурация для бота Mattermost
"""
import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Mattermost настройки
    MATTERMOST_URL = os.getenv('MATTERMOST_URL', 'https://your-mattermost-server.com')
    MATTERMOST_TOKEN = os.getenv('MATTERMOST_TOKEN')
    MATTERMOST_USERNAME = os.getenv('MATTERMOST_USERNAME', 'standup-bot')
    MATTERMOST_TEAM = os.getenv('MATTERMOST_TEAM')  # Команда в Mattermost
    MATTERMOST_CHANNEL_ID = os.getenv('MATTERMOST_CHANNEL_ID')  # ID канала для отчетов
    MATTERMOST_SSL_VERIFY = os.getenv('MATTERMOST_SSL_VERIFY', 'true').lower() == 'true'
    
    # Jira настройки (on-premise)
    JIRA_URL = os.getenv('JIRA_URL', 'https://jira.your-company.com')
    JIRA_USERNAME = os.getenv('JIRA_USERNAME')
    JIRA_API_TOKEN = os.getenv('JIRA_API_TOKEN')  # Для новых версий Jira Server
    JIRA_PASSWORD = os.getenv('JIRA_PASSWORD')    # Для старых версий on-premise
    JIRA_AUTH_METHOD = os.getenv('JIRA_AUTH_METHOD', 'password')  # 'token' или 'password'
    JIRA_VERIFY_SSL = os.getenv('JIRA_VERIFY_SSL', 'true').lower() == 'true'
    
    # Tempo API настройки
    TEMPO_API_TOKEN = os.getenv('TEMPO_API_TOKEN')
    TEMPO_API_URL = os.getenv('TEMPO_API_URL', 'https://api.tempo.io/core/3')  # Или ваш on-premise URL
    TEMPO_VERIFY_SSL = os.getenv('TEMPO_VERIFY_SSL', 'true').lower() == 'true'
    
    # База данных
    DATABASE_PATH = os.getenv('DATABASE_PATH', 'standup_bot.db')
    
    # Администраторы (email адреса, разделенные запятыми)
    ADMIN_EMAILS = os.getenv('ADMIN_EMAILS', '').split(',')
    
    # Расписание проверки (время в формате HH:MM)
    CHECK_TIME = os.getenv('CHECK_TIME', '09:00')
    
    # Часовой пояс
    TIMEZONE = os.getenv('TIMEZONE', 'Europe/Moscow')
    
    # Логирование
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
    LOG_FILE = os.getenv('LOG_FILE', 'standup_bot.log')

config = Config()
