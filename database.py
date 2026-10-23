"""
Модуль для работы с базой данных SQLite
"""

import contextlib
import logging
import re
import sqlite3
from datetime import date, timedelta

from config import config
from crypto_utils import password_crypto

logger = logging.getLogger(__name__)


class DatabaseManager:
    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or config.DATABASE_PATH
        self.init_database()

    @contextlib.contextmanager
    def _connect(self):
        """Соединение с БД: коммит при успехе, откат при ошибке, гарантированное закрытие"""
        conn = sqlite3.connect(self.db_path, timeout=30)
        try:
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def _normalize_email(user_email: str) -> str:
        return (user_email or "").strip().lower()

    def init_database(self):
        """Инициализация базы данных и создание таблиц"""
        try:
            with self._connect() as conn:
                cursor = conn.cursor()
                cursor.execute("PRAGMA journal_mode=WAL")

                # Таблица настроек подключения к Jira для пользователей
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS user_jira_settings (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_email TEXT UNIQUE NOT NULL,
                        user_id TEXT NOT NULL,
                        jira_username TEXT NOT NULL,
                        jira_password TEXT NOT NULL,
                        last_test_success BOOLEAN DEFAULT 0,
                        last_test_at TIMESTAMP,
                        connection_attempts INTEGER DEFAULT 0,
                        is_blocked BOOLEAN DEFAULT 0,
                        blocked_at TIMESTAMP,
                        last_connection_error TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                # Добавляем новые поля, если таблица уже существует (миграция)
                with contextlib.suppress(sqlite3.OperationalError):
                    cursor.execute("ALTER TABLE user_jira_settings ADD COLUMN connection_attempts INTEGER DEFAULT 0")

                with contextlib.suppress(sqlite3.OperationalError):
                    cursor.execute("ALTER TABLE user_jira_settings ADD COLUMN is_blocked BOOLEAN DEFAULT 0")

                with contextlib.suppress(sqlite3.OperationalError):
                    cursor.execute("ALTER TABLE user_jira_settings ADD COLUMN blocked_at TIMESTAMP")

                with contextlib.suppress(sqlite3.OperationalError):
                    cursor.execute("ALTER TABLE user_jira_settings ADD COLUMN last_connection_error TEXT")

                # Тип авторизации: 'pat' - Personal Access Token, 'password' - устаревший вход по логину/паролю,
                # 'pat_reset' - токен сброшен из-за смены ключа шифрования (нужен повторный вход).
                # Все записи, созданные до перехода на PAT, получают 'password' и считаются отключенными.
                with contextlib.suppress(sqlite3.OperationalError):
                    cursor.execute("ALTER TABLE user_jira_settings ADD COLUMN auth_type TEXT DEFAULT 'password'")

                # Когда пользователю отправлено уведомление о переходе на PAT
                with contextlib.suppress(sqlite3.OperationalError):
                    cursor.execute("ALTER TABLE user_jira_settings ADD COLUMN pat_migration_notified_at TIMESTAMP")

                # Служебные настройки приложения (например, отпечаток ключа шифрования)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS app_settings (
                        key TEXT PRIMARY KEY,
                        value TEXT
                    )
                """)

                # Таблица подписок на проекты
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS project_subscriptions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        project_key TEXT NOT NULL,
                        project_name TEXT,
                        mattermost_channel_id TEXT NOT NULL,
                        mattermost_team_id TEXT,
                        subscribed_by_user_id TEXT NOT NULL,
                        subscribed_by_email TEXT,
                        active BOOLEAN DEFAULT 1,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(project_key, mattermost_channel_id)
                    )
                """)

                # Таблица для истории уведомлений
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS notification_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        project_key TEXT NOT NULL,
                        issue_key TEXT NOT NULL,
                        notification_type TEXT NOT NULL, -- 'time_exceeded' или 'deadline_overdue'
                        assignee_email TEXT,
                        assignee_name TEXT,
                        channel_id TEXT NOT NULL,
                        issue_summary TEXT,
                        planned_hours REAL DEFAULT 0,
                        actual_hours REAL DEFAULT 0,
                        due_date DATE,
                        notification_date DATE NOT NULL,
                        sent_to_channel BOOLEAN DEFAULT 0,
                        sent_to_assignee BOOLEAN DEFAULT 0,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(issue_key, notification_type, channel_id, notification_date)
                    )
                """)

                # Миграция: уникальность уведомления теперь учитывает канал
                cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='notification_history'")
                table_sql = (cursor.fetchone() or [""])[0] or ""
                if "UNIQUE(issue_key, notification_type, notification_date)" in table_sql:
                    cursor.execute("ALTER TABLE notification_history RENAME TO notification_history_old")
                    cursor.execute("DROP INDEX IF EXISTS idx_notification_date")
                    cursor.execute(
                        table_sql.replace(
                            "UNIQUE(issue_key, notification_type, notification_date)",
                            "UNIQUE(issue_key, notification_type, channel_id, notification_date)",
                        )
                    )
                    cursor.execute(
                        """
                        INSERT OR IGNORE INTO notification_history
                        SELECT * FROM notification_history_old
                    """
                    )
                    cursor.execute("DROP TABLE notification_history_old")

                # Таблица для кеширования информации о задачах
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS issue_cache (
                        issue_key TEXT PRIMARY KEY,
                        project_key TEXT NOT NULL,
                        summary TEXT,
                        assignee_email TEXT,
                        assignee_name TEXT,
                        status TEXT,
                        due_date DATE,
                        original_estimate REAL DEFAULT 0,
                        time_spent REAL DEFAULT 0,
                        remaining_estimate REAL DEFAULT 0,
                        last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                # Таблица для хранения производственного календаря
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS production_calendar (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        year INTEGER NOT NULL,
                        holiday_date DATE NOT NULL,
                        is_holiday BOOLEAN DEFAULT 1,
                        is_weekend BOOLEAN DEFAULT 0,
                        description TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(year, holiday_date)
                    )
                """)

                # Таблица для отслеживания загрузки календарей
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS calendar_metadata (
                        year INTEGER PRIMARY KEY,
                        is_loaded BOOLEAN DEFAULT 0,
                        last_check_date DATE,
                        last_update_date DATE,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                # Индексы для оптимизации
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_email ON user_jira_settings(user_email)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_project_key ON project_subscriptions(project_key)")
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS idx_channel_id ON project_subscriptions(mattermost_channel_id)"
                )
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS idx_notification_date ON notification_history(notification_date)"
                )
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_issue_project ON issue_cache(project_key)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_issue_assignee ON issue_cache(assignee_email)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_calendar_year ON production_calendar(year)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_calendar_date ON production_calendar(holiday_date)")

                conn.commit()
                logger.info("База данных инициализирована успешно")

        except Exception as e:
            logger.error(f"Ошибка инициализации базы данных: {e}")
            raise

    def _validate_email(self, email: str) -> bool:
        """Валидация email адреса"""
        pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
        return re.match(pattern, email.strip()) is not None

    def _sanitize_input(self, text: str, max_length: int = 255) -> str:
        """Очистка и ограничение длины входных данных"""
        if not text:
            return ""
        return text.strip()[:max_length]

    def save_user_jira_settings(self, user_email: str, user_id: str, jira_username: str, jira_token: str) -> bool:
        """Сохранить настройки подключения к Jira (Personal Access Token) для пользователя"""
        # Валидация входных данных
        # Если email валидный - используем его, иначе используем user_id как идентификатор
        if self._validate_email(user_email):
            user_email = self._sanitize_input(user_email.lower())
        else:
            # Если email невалидный, используем user_id как идентификатор
            user_email = f"user_{self._sanitize_input(user_id)}"
            logger.info(f"Используем user_id как идентификатор: {user_email}")

        user_id = self._sanitize_input(user_id)
        jira_username = self._sanitize_input(jira_username)

        # Проверка на пустые обязательные поля
        if not all([user_email, user_id, jira_username, jira_token]):
            logger.error("Пустые обязательные поля при сохранении настроек Jira")
            return False

        # Ограничение длины токена
        if len(jira_token) > 500:
            logger.error("Токен слишком длинный")
            return False

        try:
            # Шифруем токен перед сохранением (хранится в колонке jira_password)
            encrypted_token = password_crypto.encrypt_password(jira_token)

            with self._connect() as conn:
                cursor = conn.cursor()
                # Проверяем, существует ли уже запись для этого пользователя
                cursor.execute("SELECT id FROM user_jira_settings WHERE user_email = ?", (user_email,))
                existing = cursor.fetchone()

                if existing:
                    # Обновляем существующую запись и сбрасываем счетчик попыток
                    cursor.execute(
                        """
                        UPDATE user_jira_settings
                        SET user_id = ?, jira_username = ?, jira_password = ?, auth_type = 'pat',
                            connection_attempts = 0, is_blocked = 0,
                            blocked_at = NULL, last_connection_error = NULL,
                            last_test_success = 1, last_test_at = CURRENT_TIMESTAMP,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE user_email = ?
                    """,
                        (user_id, jira_username, encrypted_token, user_email),
                    )
                else:
                    # Создаем новую запись
                    cursor.execute(
                        """
                        INSERT INTO user_jira_settings
                        (user_email, user_id, jira_username, jira_password, auth_type,
                         last_test_success, last_test_at, updated_at)
                        VALUES (?, ?, ?, ?, 'pat', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    """,
                        (user_email, user_id, jira_username, encrypted_token),
                    )
                conn.commit()
                logger.info(
                    f"Настройки Jira сохранены для пользователя {user_email} (PAT зашифрован, счетчик попыток сброшен)"
                )
                return True
        except Exception as e:
            logger.error(f"Ошибка сохранения настроек Jira для {user_email}: {e}")
            return False

    def get_user_jira_settings(self, user_email: str) -> tuple[str, str, str, str] | None:
        """Получить настройки подключения к Jira (user_id, jira_username, PAT, last_test_success).

        Возвращает только записи с авторизацией по PAT: устаревшие записи с логином/паролем
        считаются отключенными.
        """
        user_email = self._normalize_email(user_email)
        try:
            with self._connect() as conn:
                cursor = conn.cursor()

                # Сначала пробуем найти по email
                cursor.execute(
                    """
                    SELECT user_id, jira_username, jira_password, last_test_success
                    FROM user_jira_settings
                    WHERE user_email = ? AND auth_type = 'pat'
                """,
                    (user_email,),
                )
                result = cursor.fetchone()

                # Если не найден по email, пробуем найти по user_id (если email начинается с "user_")
                if not result and user_email.startswith("user_"):
                    user_id = user_email[5:]  # Убираем префикс "user_"
                    cursor.execute(
                        """
                        SELECT user_id, jira_username, jira_password, last_test_success
                        FROM user_jira_settings
                        WHERE user_id = ? AND auth_type = 'pat'
                    """,
                        (user_id,),
                    )
                    result = cursor.fetchone()

                if result:
                    user_id, jira_username, encrypted_token, last_test_success = result

                    try:
                        decrypted_token = password_crypto.decrypt_password(encrypted_token)
                        return (user_id, jira_username, decrypted_token, last_test_success)
                    except Exception as decrypt_error:
                        logger.error(f"Ошибка расшифровки токена для {user_email}: {decrypt_error}")
                        return None

                return None
        except Exception as e:
            logger.error(f"Ошибка получения настроек Jira для {user_email}: {e}")
            return None

    def update_jira_test_result(self, user_email: str, success: bool) -> bool:
        """Обновить результат тестирования подключения к Jira"""
        user_email = self._normalize_email(user_email)
        try:
            with self._connect() as conn:
                cursor = conn.cursor()
                if success:
                    # При успешном подключении сбрасываем счетчик попыток и разблокируем
                    cursor.execute(
                        """
                        UPDATE user_jira_settings
                        SET last_test_success = ?, last_test_at = CURRENT_TIMESTAMP,
                            connection_attempts = 0, is_blocked = 0, blocked_at = NULL,
                            last_connection_error = NULL
                        WHERE user_email = ?
                    """,
                        (success, user_email),
                    )
                else:
                    cursor.execute(
                        """
                        UPDATE user_jira_settings
                        SET last_test_success = ?, last_test_at = CURRENT_TIMESTAMP
                        WHERE user_email = ?
                    """,
                        (success, user_email),
                    )
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Ошибка обновления результата теста для {user_email}: {e}")
            return False

    def increment_connection_attempts(self, user_email: str, error_message: str | None = None) -> tuple[int, bool]:
        """Увеличить счетчик попыток подключения и проверить, нужно ли заблокировать"""
        user_email = self._normalize_email(user_email)
        try:
            with self._connect() as conn:
                cursor = conn.cursor()
                # Получаем текущее количество попыток
                cursor.execute(
                    """
                    SELECT connection_attempts, is_blocked
                    FROM user_jira_settings
                    WHERE user_email = ?
                """,
                    (user_email,),
                )
                result = cursor.fetchone()

                if not result:
                    return 0, False

                current_attempts, is_blocked = result

                # Если уже заблокирован, не увеличиваем счетчик
                if is_blocked:
                    return current_attempts, True

                # Увеличиваем счетчик
                new_attempts = current_attempts + 1
                # Блокируем сразу при первой ошибке аутентификации,
                # чтобы не делать лишних запросов к Jira с неправильным паролем
                should_block = new_attempts >= 1

                if should_block:
                    # Блокируем пользователя
                    cursor.execute(
                        """
                        UPDATE user_jira_settings
                        SET connection_attempts = ?, is_blocked = 1,
                            blocked_at = CURRENT_TIMESTAMP,
                            last_connection_error = ?
                        WHERE user_email = ?
                    """,
                        (new_attempts, error_message or "Превышено максимальное количество попыток", user_email),
                    )
                else:
                    # Просто увеличиваем счетчик
                    cursor.execute(
                        """
                        UPDATE user_jira_settings
                        SET connection_attempts = ?, last_connection_error = ?
                        WHERE user_email = ?
                    """,
                        (new_attempts, error_message, user_email),
                    )

                conn.commit()
                return new_attempts, should_block
        except Exception as e:
            logger.error(f"Ошибка обновления счетчика попыток для {user_email}: {e}")
            return 0, False

    def reset_connection_attempts(self, user_email: str) -> bool:
        """Сбросить счетчик попыток подключения (при смене пароля)"""
        user_email = self._normalize_email(user_email)
        try:
            with self._connect() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    UPDATE user_jira_settings
                    SET connection_attempts = 0, is_blocked = 0,
                        blocked_at = NULL, last_connection_error = NULL
                    WHERE user_email = ?
                """,
                    (user_email,),
                )
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Ошибка сброса счетчика попыток для {user_email}: {e}")
            return False

    def is_user_blocked(self, user_email: str) -> bool:
        """Проверить, заблокирован ли пользователь"""
        user_email = self._normalize_email(user_email)
        try:
            with self._connect() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT is_blocked FROM user_jira_settings WHERE user_email = ?
                """,
                    (user_email,),
                )
                result = cursor.fetchone()
                return result[0] if result else False
        except Exception as e:
            logger.error(f"Ошибка проверки блокировки для {user_email}: {e}")
            return False

    def get_user_block_info(self, user_email: str) -> tuple[int, bool, str | None] | None:
        """Получить информацию о блокировке пользователя: (попытки, заблокирован, дата блокировки)"""
        user_email = self._normalize_email(user_email)
        try:
            with self._connect() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT connection_attempts, is_blocked, blocked_at
                    FROM user_jira_settings WHERE user_email = ?
                """,
                    (user_email,),
                )
                result = cursor.fetchone()
                if result:
                    return (result[0], bool(result[1]), result[2])
                return None
        except Exception as e:
            logger.error(f"Ошибка получения информации о блокировке для {user_email}: {e}")
            return None

    def get_legacy_users_to_notify(self) -> list[tuple[str, str, str]]:
        """Пользователи без действующего PAT, которым еще не отправлено уведомление о повторном входе.

        Возвращает список (user_email, user_id, auth_type): 'password' - старый вход по логину/паролю,
        'pat_reset' - токен сброшен из-за смены ключа шифрования.
        """
        try:
            with self._connect() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT user_email, user_id, COALESCE(auth_type, 'password') FROM user_jira_settings
                    WHERE COALESCE(auth_type, 'password') != 'pat' AND pat_migration_notified_at IS NULL
                """
                )
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"Ошибка получения пользователей без действующего токена: {e}")
            return []

    def disable_legacy_user(self, user_email: str, notified: bool) -> bool:
        """Отключить пользователя без действующего PAT: удалить сохраненный пароль/токен.

        notified=True отмечает, что уведомление о повторном входе доставлено (повторно не отправляется).
        """
        user_email = self._normalize_email(user_email)
        try:
            with self._connect() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    UPDATE user_jira_settings
                    SET jira_password = '', last_test_success = 0,
                        pat_migration_notified_at = CASE WHEN ? THEN CURRENT_TIMESTAMP ELSE NULL END,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE user_email = ? AND COALESCE(auth_type, 'password') != 'pat'
                """,
                    (notified, user_email),
                )
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Ошибка отключения пользователя {user_email}: {e}")
            return False

    def get_app_setting(self, key: str) -> str | None:
        """Получить служебную настройку приложения"""
        try:
            with self._connect() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT value FROM app_settings WHERE key = ?", (key,))
                result = cursor.fetchone()
                return result[0] if result else None
        except Exception as e:
            logger.error(f"Ошибка получения настройки {key}: {e}")
            return None

    def reset_tokens_if_key_changed(self, key_fingerprint: str) -> int:
        """Сбросить сохраненные токены, если ключ шифрования изменился (или еще не был зафиксирован).

        Токены, зашифрованные другим ключом, расшифровать нельзя: пользователей помечаем 'pat_reset',
        им будет отправлена просьба войти заново. Возвращает количество сброшенных токенов.
        """
        try:
            with self._connect() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT value FROM app_settings WHERE key = 'encryption_key_fingerprint'")
                row = cursor.fetchone()
                if row and row[0] == key_fingerprint:
                    return 0

                cursor.execute(
                    """
                    UPDATE user_jira_settings
                    SET jira_password = '', auth_type = 'pat_reset', last_test_success = 0,
                        pat_migration_notified_at = NULL, updated_at = CURRENT_TIMESTAMP
                    WHERE auth_type = 'pat'
                """
                )
                reset_count = cursor.rowcount
                cursor.execute(
                    """
                    INSERT INTO app_settings (key, value) VALUES ('encryption_key_fingerprint', ?)
                    ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                    (key_fingerprint,),
                )
                conn.commit()
                if reset_count:
                    logger.warning(f"Ключ шифрования изменился: сброшено токенов - {reset_count}")
                return reset_count
        except Exception as e:
            logger.error(f"Ошибка проверки ключа шифрования: {e}")
            raise

    def get_all_jira_users(self) -> list[tuple[str, str, str]]:
        """Все пользователи с настройками Jira: (user_email, jira_username, auth_type)"""
        try:
            with self._connect() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT user_email, jira_username, COALESCE(auth_type, 'password') FROM user_jira_settings"
                )
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"Ошибка получения списка пользователей: {e}")
            return []

    def delete_user_jira_settings(self, user_email: str) -> bool:
        """Удалить настройки Jira пользователя"""
        user_email = self._normalize_email(user_email)
        try:
            with self._connect() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM user_jira_settings WHERE user_email = ?", (user_email,))
                conn.commit()
                if cursor.rowcount > 0:
                    logger.info(f"Настройки Jira удалены для пользователя {user_email}")
                    return True
                return False
        except Exception as e:
            logger.error(f"Ошибка удаления настроек Jira для {user_email}: {e}")
            return False

    def subscribe_to_project(
        self, project_key: str, project_name: str, channel_id: str, team_id: str, user_id: str, user_email: str
    ) -> bool:
        """Подписать канал на мониторинг проекта"""
        user_email = self._normalize_email(user_email)
        try:
            with self._connect() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO project_subscriptions
                    (project_key, project_name, mattermost_channel_id, mattermost_team_id,
                     subscribed_by_user_id, subscribed_by_email, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                    (project_key, project_name, channel_id, team_id, user_id, user_email),
                )
                conn.commit()
                logger.info(f"Канал {channel_id} подписан на проект {project_key}")
                return True
        except Exception as e:
            logger.error(f"Ошибка подписки на проект {project_key}: {e}")
            return False

    def unsubscribe_from_project(self, project_key: str, channel_id: str) -> bool:
        """Отписать канал от мониторинга проекта"""
        try:
            with self._connect() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    UPDATE project_subscriptions
                    SET active = 0, updated_at = CURRENT_TIMESTAMP
                    WHERE project_key = ? AND mattermost_channel_id = ?
                """,
                    (project_key, channel_id),
                )
                if cursor.rowcount > 0:
                    conn.commit()
                    logger.info(f"Канал {channel_id} отписан от проекта {project_key}")
                    return True
                else:
                    logger.warning(f"Подписка на проект {project_key} в канале {channel_id} не найдена")
                    return False
        except Exception as e:
            logger.error(f"Ошибка отписки от проекта {project_key}: {e}")
            return False

    def get_active_subscriptions(self) -> list[tuple]:
        """Получить список активных подписок на проекты"""
        try:
            with self._connect() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT project_key, project_name, mattermost_channel_id,
                           mattermost_team_id, subscribed_by_email
                    FROM project_subscriptions
                    WHERE active = 1
                    ORDER BY project_key
                """)
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"Ошибка получения списка подписок: {e}")
            return []

    def get_subscriptions_by_channel(self, channel_id: str) -> list[tuple]:
        """Получить подписки для конкретного канала"""
        try:
            with self._connect() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT project_key, project_name, subscribed_by_email, created_at, active
                    FROM project_subscriptions
                    WHERE mattermost_channel_id = ? AND active = 1
                    ORDER BY created_at DESC
                """,
                    (channel_id,),
                )
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"Ошибка получения подписок для канала {channel_id}: {e}")
            return []

    def get_all_subscriptions(self) -> list[tuple]:
        """Получить все подписки (для администраторов)"""
        try:
            with self._connect() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT project_key, project_name, mattermost_channel_id,
                           subscribed_by_email, created_at, active
                    FROM project_subscriptions
                    ORDER BY created_at DESC
                """)
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"Ошибка получения всех подписок: {e}")
            return []

    def delete_subscription_by_id(self, project_key: str, channel_id: str) -> bool:
        """Удалить конкретную подписку (для администраторов)"""
        try:
            with self._connect() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    DELETE FROM project_subscriptions
                    WHERE project_key = ? AND mattermost_channel_id = ?
                """,
                    (project_key, channel_id),
                )
                conn.commit()
                if cursor.rowcount > 0:
                    logger.info(f"Подписка {project_key} в канале {channel_id} удалена")
                    return True
                return False
        except Exception as e:
            logger.error(f"Ошибка удаления подписки {project_key}/{channel_id}: {e}")
            return False

    def save_notification(
        self,
        project_key: str,
        issue_key: str,
        notification_type: str,
        assignee_email: str,
        assignee_name: str,
        channel_id: str,
        issue_summary: str,
        planned_hours: float,
        actual_hours: float,
        due_date: str | None = None,
    ) -> bool:
        """Сохранить информацию об отправленном уведомлении"""
        try:
            with self._connect() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO notification_history
                    (project_key, issue_key, notification_type, assignee_email, assignee_name,
                     channel_id, issue_summary, planned_hours, actual_hours, due_date, notification_date)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        project_key,
                        issue_key,
                        notification_type,
                        assignee_email,
                        assignee_name,
                        channel_id,
                        issue_summary,
                        planned_hours,
                        actual_hours,
                        due_date,
                        # Дата в часовом поясе бота (DATE('now') в SQLite - это UTC)
                        date.today().isoformat(),
                    ),
                )
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Ошибка сохранения уведомления для {issue_key}: {e}")
            return False

    def was_notified_today(self, issue_key: str, notification_type: str, channel_id: str) -> bool:
        """Было ли уже отправлено такое уведомление в этот канал сегодня"""
        try:
            with self._connect() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT 1 FROM notification_history
                    WHERE issue_key = ? AND notification_type = ? AND channel_id = ? AND notification_date = ?
                """,
                    (issue_key, notification_type, channel_id, date.today().isoformat()),
                )
                return cursor.fetchone() is not None
        except Exception as e:
            logger.error(f"Ошибка проверки истории уведомлений для {issue_key}: {e}")
            return False

    def update_issue_cache(
        self,
        issue_key: str,
        project_key: str,
        summary: str,
        assignee_email: str,
        assignee_name: str,
        status: str,
        due_date: str,
        original_estimate: float,
        time_spent: float,
        remaining_estimate: float,
    ) -> bool:
        """Обновить кеш информации о задаче"""
        try:
            with self._connect() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO issue_cache
                    (issue_key, project_key, summary, assignee_email, assignee_name, status,
                     due_date, original_estimate, time_spent, remaining_estimate, last_updated)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                    (
                        issue_key,
                        project_key,
                        summary,
                        assignee_email,
                        assignee_name,
                        status,
                        due_date,
                        original_estimate,
                        time_spent,
                        remaining_estimate,
                    ),
                )
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Ошибка обновления кеша для задачи {issue_key}: {e}")
            return False

    def get_notification_history(self, days: int = 7, channel_id: str | None = None) -> list[tuple]:
        """История отправленных уведомлений за последние дни (по всем каналам или по одному каналу).

        Возвращает (notification_date, project_key, issue_key, notification_type, assignee_name).
        """
        since = (date.today() - timedelta(days=days - 1)).isoformat()
        query = """
            SELECT notification_date, project_key, issue_key, notification_type, assignee_name
            FROM notification_history
            WHERE notification_date >= ?
        """
        params: list = [since]
        if channel_id:
            query += " AND channel_id = ?"
            params.append(channel_id)
        query += " ORDER BY notification_date DESC, project_key, issue_key"

        try:
            with self._connect() as conn:
                cursor = conn.cursor()
                cursor.execute(query, params)
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"Ошибка получения истории уведомлений: {e}")
            return []

    def get_last_notification_date(self) -> str | None:
        """Дата последнего отправленного уведомления"""
        try:
            with self._connect() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT MAX(notification_date) FROM notification_history")
                result = cursor.fetchone()
                return result[0] if result else None
        except Exception as e:
            logger.error(f"Ошибка получения даты последнего уведомления: {e}")
            return None

    def save_calendar_holidays(
        self, year: int, holidays: list[date], descriptions: dict[date, str] | None = None
    ) -> bool:
        """Сохранить выходные и праздничные дни календаря на год"""
        try:
            with self._connect() as conn:
                cursor = conn.cursor()

                # Удаляем старые данные для этого года
                cursor.execute("DELETE FROM production_calendar WHERE year = ?", (year,))

                # Сохраняем новые данные
                for holiday_date in holidays:
                    description = descriptions.get(holiday_date, "") if descriptions else ""
                    # Определяем, является ли день выходным (суббота/воскресенье) или праздничным
                    is_weekend = holiday_date.weekday() >= 5  # 5 = суббота, 6 = воскресенье
                    is_holiday = not is_weekend  # Если не выходной, то праздничный

                    cursor.execute(
                        """
                        INSERT OR REPLACE INTO production_calendar
                        (year, holiday_date, is_holiday, is_weekend, description)
                        VALUES (?, ?, ?, ?, ?)
                    """,
                        (year, holiday_date.isoformat(), is_holiday, is_weekend, description),
                    )

                # Обновляем метаданные
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO calendar_metadata
                    (year, is_loaded, last_update_date, updated_at)
                    VALUES (?, 1, DATE('now'), CURRENT_TIMESTAMP)
                """,
                    (year,),
                )

                conn.commit()
                logger.info(f"Сохранено {len(holidays)} выходных и праздничных дней для {year} года")
                return True
        except Exception as e:
            logger.error(f"Ошибка сохранения календаря для {year} года: {e}")
            return False

    def is_holiday(self, check_date: date) -> bool:
        """Проверить, является ли день выходным или праздничным"""
        try:
            with self._connect() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT COUNT(*) FROM production_calendar
                    WHERE holiday_date = ?
                """,
                    (check_date.isoformat(),),
                )
                result = cursor.fetchone()
                return result[0] > 0 if result else False
        except Exception as e:
            logger.error(f"Ошибка проверки выходного дня {check_date}: {e}")
            return False

    def is_calendar_loaded(self, year: int) -> bool:
        """Проверить, загружен ли календарь на год"""
        try:
            with self._connect() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT is_loaded FROM calendar_metadata WHERE year = ?
                """,
                    (year,),
                )
                result = cursor.fetchone()
                return result[0] if result else False
        except Exception as e:
            logger.error(f"Ошибка проверки загрузки календаря для {year} года: {e}")
            return False

    def update_calendar_check_date(self, year: int) -> bool:
        """Обновить дату последней проверки календаря"""
        try:
            with self._connect() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO calendar_metadata (year, last_check_date, updated_at)
                    VALUES (?, DATE('now'), CURRENT_TIMESTAMP)
                    ON CONFLICT(year) DO UPDATE SET
                        last_check_date = excluded.last_check_date,
                        updated_at = excluded.updated_at
                """,
                    (year,),
                )
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Ошибка обновления даты проверки календаря для {year} года: {e}")
            return False

    def get_calendar_check_date(self, year: int) -> str | None:
        """Получить дату последней проверки календаря"""
        try:
            with self._connect() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT last_check_date FROM calendar_metadata WHERE year = ?
                """,
                    (year,),
                )
                result = cursor.fetchone()
                return result[0] if result else None
        except Exception as e:
            logger.error(f"Ошибка получения даты проверки календаря для {year} года: {e}")
            return None


# Глобальный экземпляр менеджера БД
db_manager = DatabaseManager()
