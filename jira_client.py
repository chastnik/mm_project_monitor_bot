"""
Клиент для работы с Jira API (без Tempo)
"""
import logging
from datetime import datetime
from typing import Optional, Dict
from jira import JIRA
from config import config

logger = logging.getLogger(__name__)

class JiraClient:
    def __init__(self):
        self.jira_client = None
        self.connect()
    
    def connect(self):
        """Подключение к Jira"""
        try:
            # Настройки подключения для on-premise Jira
            options = {
                'server': config.JIRA_URL,
                'verify': getattr(config, 'JIRA_VERIFY_SSL', True),
            }
            
            # Аутентификация для on-premise Jira
            if hasattr(config, 'JIRA_AUTH_METHOD') and config.JIRA_AUTH_METHOD.lower() == 'token':
                # Для Jira Server с API токенами
                self.jira_client = JIRA(
                    options=options,
                    basic_auth=(config.JIRA_USERNAME, config.JIRA_API_TOKEN)
                )
            else:
                # Для on-premise Jira с паролем
                self.jira_client = JIRA(
                    options=options,
                    basic_auth=(config.JIRA_USERNAME, config.JIRA_PASSWORD)
                )
            
            logger.info("Успешно подключились к Jira")
        except Exception as e:
            logger.error(f"Ошибка подключения к Jira: {e}")
            raise
    
    def get_user_by_email(self, email: str) -> Optional[Dict]:
        """Найти пользователя Jira по email"""
        try:
            # Для on-premise Jira поиск может отличаться
            users = self.jira_client.search_users(query=email, maxResults=10)
            
            for user in users:
                user_email = getattr(user, 'emailAddress', None)
                if user_email and user_email.lower() == email.lower():
                    return {
                        'username': getattr(user, 'name', None) or getattr(user, 'key', None),
                        'accountId': getattr(user, 'accountId', None) or getattr(user, 'name', None),
                        'displayName': getattr(user, 'displayName', email),
                        'emailAddress': user_email
                    }
            
            logger.warning(f"Пользователь с email {email} не найден в Jira")
            return None
            
        except Exception as e:
            logger.error(f"Ошибка поиска пользователя {email}: {e}")
            return None
    
    def get_current_date(self) -> str:
        """Получить текущую дату в формате YYYY-MM-DD"""
        return datetime.now().strftime('%Y-%m-%d')
    
    def test_connection(self) -> bool:
        """Тестирование подключения к Jira"""
        try:
            current_user = self.jira_client.current_user()
            projects = self.jira_client.projects()
            logger.info(f"Подключение к Jira работает. Пользователь: {current_user}, проектов: {len(projects)}")
            return True
        except Exception as e:
            logger.error(f"Ошибка тестирования подключения к Jira: {e}")
            return False

# Глобальный экземпляр для обратной совместимости (если нужен)
jira_client = JiraClient()
