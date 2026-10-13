"""
Клиент для работы с Jira с персональными настройками пользователей
"""

import logging

from jira import JIRA
from jira.exceptions import JIRAError

from auth_messages import token_invalid_block_message
from config import config
from database import db_manager

logger = logging.getLogger(__name__)

# Импортируем mattermost_client для отправки уведомлений
try:
    from mattermost_client import mattermost_client
except ImportError:
    mattermost_client = None
    logger.warning("mattermost_client не доступен для отправки уведомлений")


# Размер страницы при выгрузке задач (максимум, который по умолчанию отдает Jira Server / Data Center)
JIRA_PAGE_SIZE = 1000


def _is_auth_error(error: JIRAError) -> bool:
    """Ошибка аутентификации (неверный/истекший/отозванный токен)"""
    error_message = str(error).lower()
    return (
        error.status_code in (401, 403)
        or "authentication" in error_message
        or "unauthorized" in error_message
        or "credentials" in error_message
    )


def _create_client(token: str) -> JIRA:
    """Создать клиент Jira Server/Data Center с авторизацией по Personal Access Token (Bearer)"""
    return JIRA(
        server=config.JIRA_URL,
        token_auth=token,
        options={"verify": config.JIRA_VERIFY_SSL, "timeout": 30},
    )


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

        _user_id, _jira_username, jira_token, _last_test_success = settings

        try:
            # Создаем подключение с персональным токеном
            jira_client = _create_client(jira_token)

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

            if _is_auth_error(e):
                logger.warning(f"Ошибка аутентификации для {user_email}: {error_message}")
                # Блокируем пользователя сразу при первой ошибке аутентификации
                attempts, was_blocked = db_manager.increment_connection_attempts(user_email, error_message)

                if was_blocked:
                    # Отправляем уведомление пользователю о блокировке
                    self._notify_user_about_block(user_email, attempts)
                    logger.error(
                        f"Пользователь {user_email} заблокирован - недействительный токен Jira. "
                        f"Проверки приостановлены до обновления токена."
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
            message = token_invalid_block_message()

            mattermost_client.send_direct_message_by_email(user_email, message)
            logger.info(f"Уведомление о блокировке отправлено пользователю {user_email}")
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления о блокировке пользователю {user_email}: {e}")

    def verify_token(self, token: str) -> tuple[str | None, str | None]:
        """Проверить Personal Access Token без сохранения.

        Возвращает (имя пользователя Jira, None) при успехе или (None, текст ошибки).
        """
        try:
            jira_client = _create_client(token)
            current_user = jira_client.current_user()
            if not current_user:
                return None, "Jira не вернула пользователя для этого токена"
            return current_user, None
        except JIRAError as e:
            if _is_auth_error(e):
                return None, "Токен недействителен, истек или был отозван"
            logger.error(f"Ошибка проверки токена Jira: {e}")
            return None, f"Ошибка Jira: {e.text or e}"
        except Exception as e:
            logger.error(f"Ошибка проверки токена Jira: {e}")
            return None, f"Не удалось подключиться к Jira: {e!s}"

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
                return False, "❌ Не удалось подключиться к Jira. Возможно, токен истек или был отозван."

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

    def get_project_issues(self, user_email: str, project_key: str, max_results: int = 200) -> tuple[list, int] | None:
        """Получить до max_results последних обновленных задач проекта.

        Jira ограничивает размер одной страницы (обычно 1000), поэтому задачи выгружаются постранично.
        Возвращает (задачи, общее количество задач в проекте) или None при ошибке.
        """
        jira_client = self.get_jira_client(user_email)
        if not jira_client:
            return None

        jql = f'project = "{project_key}" ORDER BY updated DESC'
        issues: list = []
        total = 0
        try:
            while len(issues) < max_results:
                page = jira_client.search_issues(
                    jql,
                    startAt=len(issues),
                    maxResults=min(JIRA_PAGE_SIZE, max_results - len(issues)),
                    expand="changelog",
                )
                total = page.total if page.total is not None else len(issues) + len(page)
                issues.extend(page)
                if not page or len(issues) >= total:
                    break
            return issues, total
        except Exception as e:
            logger.error(f"Ошибка получения задач проекта {project_key}: {e}")
            return None

    def get_issues_for_monitoring(self, user_email: str, project_key: str) -> list | None:
        """Получить задачи проекта для ежедневного мониторинга.

        Берутся все незакрытые задачи и задачи, обновленные за последние дни (недавно закрытые нужны
        для проверки трудозатрат). Выгружаются все страницы, без ограничения по количеству.
        """
        jira_client = self.get_jira_client(user_email)
        if not jira_client:
            return None

        try:
            jql = f'project = "{project_key}" AND (statusCategory != Done OR updated >= -3d) ORDER BY updated DESC'
            return jira_client.search_issues(jql, maxResults=False, expand="changelog")
        except Exception as e:
            logger.error(f"Ошибка получения задач проекта {project_key} для мониторинга: {e}")
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
