"""
Клиент для работы с Jira с персональными настройками пользователей
"""
import logging
from typing import Optional, Tuple
from jira import JIRA
from config import config
from database import db_manager

logger = logging.getLogger(__name__)

class UserJiraClient:
    def __init__(self, max_cache_size: int = 50):
        self.jira_instances = {}  # Кеш подключений для разных пользователей
        self.max_cache_size = max_cache_size
        self.cache_access_order = []  # Для LRU кеша
    
    def get_jira_client(self, user_email: str) -> Optional[JIRA]:
        """Получить клиент Jira для конкретного пользователя"""
        # Валидация входных данных
        if not user_email or not user_email.strip():
            logger.error("Пустой email пользователя")
            return None
        
        user_email = user_email.strip().lower()
        
        # Проверяем кеш
        if user_email in self.jira_instances:
            self._update_cache_access(user_email)
            return self.jira_instances[user_email]
        
        # Получаем настройки пользователя
        settings = db_manager.get_user_jira_settings(user_email)
        if not settings:
            logger.warning(f"Настройки Jira не найдены для пользователя {user_email}")
            return None
        
        user_id, jira_username, jira_password, last_test_success = settings
        
        try:
            # Создаем подключение с персональными настройками
            jira_client = JIRA(
                server=config.JIRA_URL,
                basic_auth=(jira_username, jira_password),
                options={
                    'verify': config.JIRA_VERIFY_SSL,
                    'timeout': 30
                }
            )
            
            # Тестируем подключение
            current_user = jira_client.current_user()
            logger.info(f"Успешное подключение к Jira для {user_email} как {current_user}")
            
            # Кешируем подключение
            self._add_to_cache(user_email, jira_client)
            
            # Обновляем результат теста
            db_manager.update_jira_test_result(user_email, True)
            
            return jira_client
            
        except Exception as e:
            logger.error(f"Ошибка подключения к Jira для {user_email}: {e}")
            db_manager.update_jira_test_result(user_email, False)
            return None
    
    def test_connection(self, user_email: str) -> Tuple[bool, str]:
        """Тестировать подключение к Jira для пользователя"""
        try:
            # Очищаем кеш для принудительного переподключения
            if user_email in self.jira_instances:
                del self.jira_instances[user_email]
            
            jira_client = self.get_jira_client(user_email)
            
            if jira_client:
                # Дополнительные тесты
                current_user = jira_client.current_user()
                projects = jira_client.projects()[:5]  # Первые 5 проектов
                
                return True, f"✅ Подключение успешно! Пользователь: {current_user}, доступно проектов: {len(projects)}"
            else:
                return False, "❌ Не удалось подключиться к Jira. Проверьте настройки."
                
        except Exception as e:
            logger.error(f"Ошибка тестирования подключения для {user_email}: {e}")
            return False, f"❌ Ошибка подключения: {str(e)}"
    
    def clear_user_cache(self, user_email: str):
        """Очистить кеш подключения для пользователя"""
        if user_email in self.jira_instances:
            del self.jira_instances[user_email]
            logger.info(f"Кеш подключения очищен для {user_email}")
    
    def get_project_info(self, user_email: str, project_key: str) -> Optional[Tuple[str, str]]:
        """Получить информацию о проекте"""
        jira_client = self.get_jira_client(user_email)
        if not jira_client:
            return None
        
        try:
            project = jira_client.project(project_key)
            return project.key, project.name
        except Exception as e:
            logger.error(f"Ошибка получения информации о проекте {project_key}: {e}")
            return None
    
    def get_project_issues(self, user_email: str, project_key: str, max_results: int = 200) -> Optional[list]:
        """Получить задачи проекта"""
        jira_client = self.get_jira_client(user_email)
        if not jira_client:
            return None
        
        try:
            jql = f'project = "{project_key}" ORDER BY updated DESC'
            issues = jira_client.search_issues(
                jql, 
                maxResults=max_results,
                expand='changelog'
            )
            return issues
        except Exception as e:
            logger.error(f"Ошибка получения задач проекта {project_key}: {e}")
            return None
    
    def _add_to_cache(self, user_email: str, jira_client):
        """Добавить подключение в кеш с управлением размером"""
        # Если кеш полный, удаляем самый старый элемент
        if len(self.jira_instances) >= self.max_cache_size:
            oldest_email = self.cache_access_order.pop(0)
            if oldest_email in self.jira_instances:
                del self.jira_instances[oldest_email]
                logger.debug(f"Удален из кеша старый клиент для {oldest_email}")
        
        self.jira_instances[user_email] = jira_client
        self.cache_access_order.append(user_email)
    
    def _update_cache_access(self, user_email: str):
        """Обновить порядок доступа в кеше (LRU)"""
        if user_email in self.cache_access_order:
            self.cache_access_order.remove(user_email)
        self.cache_access_order.append(user_email)
    
    def get_cache_stats(self) -> dict:
        """Получить статистику кеша"""
        return {
            'size': len(self.jira_instances),
            'max_size': self.max_cache_size,
            'users': list(self.jira_instances.keys())
        }

# Глобальный экземпляр
user_jira_client = UserJiraClient()
