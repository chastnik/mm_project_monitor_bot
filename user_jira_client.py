"""
Клиент для работы с Jira с персональными настройками пользователей
"""

import logging

from jira import JIRA
from jira.exceptions import JIRAError

from config import config
from database import db_manager

logger = logging.getLogger(__name__)

# Импортируем mattermost_client для отправки уведомлений
try:
    from mattermost_client import mattermost_client
except ImportError:
    mattermost_client = None
    logger.warning("mattermost_client не доступен для отправки уведомлений")


class UserJiraClient:
    def __init__(self, max_cache_size: int = 50):
        self.jira_instances = {}  # Кеш подключений для разных пользователей
        self.max_cache_size = max_cache_size
        self.cache_access_order = []  # Для LRU кеша

    def get_jira_client(self, user_email: str) -> JIRA | None:
        """Получить клиент Jira для конкретного пользователя"""
        # Валидация входных данных
        if not user_email or not user_email.strip():
            logger.error("Пустой email пользователя")
            return None

        user_email = user_email.strip().lower()

        # Проверяем, не заблокирован ли пользователь
        if db_manager.is_user_blocked(user_email):
            logger.warning(f"Пользователь {user_email} заблокирован из-за превышения лимита попыток подключения")
            return None

        # Проверяем кеш
        if user_email in self.jira_instances:
            self._update_cache_access(user_email)
            return self.jira_instances[user_email]

        # Получаем настройки пользователя
        settings = db_manager.get_user_jira_settings(user_email)
        if not settings:
            logger.warning(f"Настройки Jira не найдены для пользователя {user_email}")
            return None

        _user_id, jira_username, jira_password, _last_test_success = settings

        try:
            # Создаем подключение с персональными настройками
            jira_client = JIRA(
                server=config.JIRA_URL,
                basic_auth=(jira_username, jira_password),
                options={"verify": config.JIRA_VERIFY_SSL, "timeout": 30},
            )

            # Тестируем подключение
            current_user = jira_client.current_user()
            logger.info(f"Успешное подключение к Jira для {user_email} как {current_user}")

            # Кешируем подключение
            self._add_to_cache(user_email, jira_client)

            # Обновляем результат теста (сбрасывает счетчик попыток)
            db_manager.update_jira_test_result(user_email, True)

            return jira_client

        except JIRAError as e:
            # Обрабатываем ошибки аутентификации Jira
            error_message = str(e)
            is_auth_error = (
                e.status_code == 401
                or "authentication" in error_message.lower()
                or "unauthorized" in error_message.lower()
                or "credentials" in error_message.lower()
            )

            if is_auth_error:
                logger.warning(f"Ошибка аутентификации для {user_email}: {error_message}")
                # Блокируем пользователя сразу при первой ошибке аутентификации
                attempts, was_blocked = db_manager.increment_connection_attempts(user_email, error_message)

                if was_blocked:
                    # Отправляем уведомление пользователю о блокировке
                    self._notify_user_about_block(user_email, attempts)
                    logger.error(
                        f"Пользователь {user_email} заблокирован - неправильный пароль Jira. "
                        f"Проверки приостановлены до смены пароля."
                    )
            else:
                # Другие ошибки не считаем как попытки аутентификации
                logger.error(f"Ошибка подключения к Jira для {user_email}: {error_message}")

            db_manager.update_jira_test_result(user_email, False)
            return None

        except Exception as e:
            # Обрабатываем другие исключения
            error_message = str(e)
            logger.error(f"Ошибка подключения к Jira для {user_email}: {error_message}")
            db_manager.update_jira_test_result(user_email, False)
            return None

    def _notify_user_about_block(self, user_email: str, attempts: int):
        """Отправить уведомление пользователю о блокировке подключения"""
        if not mattermost_client:
            logger.warning("mattermost_client недоступен, не могу отправить уведомление")
            return

        try:
            message = """🔒 **Проверки приостановлены — неправильный пароль Jira**

Бот не смог подключиться к Jira с вашим текущим паролем.

**Все автоматические проверки ваших проектов приостановлены** до обновления пароля.

**Что делать:**
1. Проверьте, не изменили ли вы пароль в Jira
2. Обновите пароль в боте командой: `change_password <новый_пароль>`
   или настройте подключение заново: `setup_jira <username> <новый_пароль>`

После обновления пароля проверки возобновятся автоматически.

Если проблема сохраняется, обратитесь к администратору."""

            mattermost_client.send_direct_message_by_email(user_email, message)
            logger.info(f"Уведомление о блокировке отправлено пользователю {user_email}")
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления о блокировке пользователю {user_email}: {e}")

    def test_connection(self, user_email: str) -> tuple[bool, str]:
        """Тестировать подключение к Jira для пользователя"""
        try:
            # Очищаем кеш для принудительного переподключения
            if user_email in self.jira_instances:
                del self.jira_instances[user_email]

            jira_client = self.get_jira_client(user_email)

            if jira_client:
                # Дополнительные тесты
                current_user = jira_client.current_user()
                projects = jira_client.projects()  # Все доступные проекты

                return True, f"✅ Подключение успешно! Пользователь: {current_user}, доступно проектов: {len(projects)}"
            else:
                return False, "❌ Не удалось подключиться к Jira. Проверьте настройки."

        except Exception as e:
            logger.error(f"Ошибка тестирования подключения для {user_email}: {e}")
            return False, f"❌ Ошибка подключения: {e!s}"

    def clear_user_cache(self, user_email: str):
        """Очистить кеш подключения для пользователя"""
        if user_email in self.jira_instances:
            del self.jira_instances[user_email]
            logger.info(f"Кеш подключения очищен для {user_email}")

    def get_project_info(self, user_email: str, project_key: str) -> tuple[str, str] | None:
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

    def get_project_issues(self, user_email: str, project_key: str, max_results: int = 200) -> list | None:
        """Получить задачи проекта"""
        jira_client = self.get_jira_client(user_email)
        if not jira_client:
            return None

        try:
            jql = f'project = "{project_key}" ORDER BY updated DESC'
            issues = jira_client.search_issues(jql, maxResults=max_results, expand="changelog,worklog")
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
            "size": len(self.jira_instances),
            "max_size": self.max_cache_size,
            "users": list(self.jira_instances.keys()),
        }


# Глобальный экземпляр
user_jira_client = UserJiraClient()
