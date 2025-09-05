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
        # Убираем автоматическое подключение, так как теперь используются только персональные настройки
        logger.info("JiraClient инициализирован без глобального подключения")
    
    def connect(self):
        """Подключение к Jira - больше не используется, так как работаем только с персональными настройками пользователей"""
        logger.warning("Глобальное подключение к Jira отключено. Используйте UserJiraClient для работы с персональными настройками.")
        return False
    
    def get_user_by_email(self, email: str) -> Optional[Dict]:
        """Найти пользователя Jira по email - метод отключен, используйте UserJiraClient"""
        logger.warning("Метод get_user_by_email отключен. Используйте UserJiraClient для работы с персональными настройками.")
        return None
    
    def get_current_date(self) -> str:
        """Получить текущую дату в формате YYYY-MM-DD"""
        return datetime.now().strftime('%Y-%m-%d')
    
    def test_connection(self) -> bool:
        """Тестирование подключения к Jira - метод отключен, используйте UserJiraClient"""
        logger.warning("Метод test_connection отключен. Используйте UserJiraClient для работы с персональными настройками.")
        return False

# Глобальный экземпляр для обратной совместимости (если нужен)
jira_client = JiraClient()
