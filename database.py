"""
Модуль для работы с базой данных SQLite
"""
import sqlite3
import logging
import re
import hashlib
from typing import List, Optional, Tuple
from config import config
from crypto_utils import password_crypto

logger = logging.getLogger(__name__)

class DatabaseManager:
    def __init__(self, db_path: str = None):
        self.db_path = db_path or config.DATABASE_PATH
        self.init_database()
    
    def init_database(self):
        """Инициализация базы данных и создание таблиц"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Таблица настроек подключения к Jira для пользователей
                cursor.execute('''
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
                ''')
                
                # Добавляем новые поля, если таблица уже существует (миграция)
                try:
                    cursor.execute('ALTER TABLE user_jira_settings ADD COLUMN connection_attempts INTEGER DEFAULT 0')
                except sqlite3.OperationalError:
                    pass  # Колонка уже существует
                
                try:
                    cursor.execute('ALTER TABLE user_jira_settings ADD COLUMN is_blocked BOOLEAN DEFAULT 0')
                except sqlite3.OperationalError:
                    pass  # Колонка уже существует
                
                try:
                    cursor.execute('ALTER TABLE user_jira_settings ADD COLUMN blocked_at TIMESTAMP')
                except sqlite3.OperationalError:
                    pass  # Колонка уже существует
                
                try:
                    cursor.execute('ALTER TABLE user_jira_settings ADD COLUMN last_connection_error TEXT')
                except sqlite3.OperationalError:
                    pass  # Колонка уже существует
                
                # Таблица подписок на проекты
                cursor.execute('''
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
                ''')
                
                # Таблица для истории уведомлений
                cursor.execute('''
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
                        UNIQUE(issue_key, notification_type, notification_date)
                    )
                ''')
                
                # Таблица для кеширования информации о задачах
                cursor.execute('''
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
                ''')
                
                # Индексы для оптимизации
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_email ON user_jira_settings(user_email)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_project_key ON project_subscriptions(project_key)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_channel_id ON project_subscriptions(mattermost_channel_id)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_notification_date ON notification_history(notification_date)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_issue_project ON issue_cache(project_key)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_issue_assignee ON issue_cache(assignee_email)')
                
                conn.commit()
                logger.info("База данных инициализирована успешно")
                
        except Exception as e:
            logger.error(f"Ошибка инициализации базы данных: {e}")
            raise
    
    def _validate_email(self, email: str) -> bool:
        """Валидация email адреса"""
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return re.match(pattern, email.strip()) is not None
    
    def _sanitize_input(self, text: str, max_length: int = 255) -> str:
        """Очистка и ограничение длины входных данных"""
        if not text:
            return ""
        return text.strip()[:max_length]
    
    def save_user_jira_settings(self, user_email: str, user_id: str, jira_username: str, jira_password: str) -> bool:
        """Сохранить настройки подключения к Jira для пользователя"""
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
        if not all([user_email, user_id, jira_username, jira_password]):
            logger.error("Пустые обязательные поля при сохранении настроек Jira")
            return False
        
        # Ограничение длины пароля
        if len(jira_password) > 500:
            logger.error("Пароль слишком длинный")
            return False
        
        try:
            # Шифруем пароль перед сохранением
            encrypted_password = password_crypto.encrypt_password(jira_password)
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                # Проверяем, существует ли уже запись для этого пользователя
                cursor.execute('SELECT id FROM user_jira_settings WHERE user_email = ?', (user_email,))
                existing = cursor.fetchone()
                
                if existing:
                    # Обновляем существующую запись и сбрасываем счетчик попыток
                    cursor.execute('''
                        UPDATE user_jira_settings 
                        SET user_id = ?, jira_username = ?, jira_password = ?, 
                            connection_attempts = 0, is_blocked = 0, 
                            blocked_at = NULL, last_connection_error = NULL,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE user_email = ?
                    ''', (user_id, jira_username, encrypted_password, user_email))
                else:
                    # Создаем новую запись
                    cursor.execute('''
                        INSERT INTO user_jira_settings 
                        (user_email, user_id, jira_username, jira_password, updated_at)
                        VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                    ''', (user_email, user_id, jira_username, encrypted_password))
                conn.commit()
                logger.info(f"Настройки Jira сохранены для пользователя {user_email} (пароль зашифрован, счетчик попыток сброшен)")
                return True
        except Exception as e:
            logger.error(f"Ошибка сохранения настроек Jira для {user_email}: {e}")
            return False
    
    def get_user_jira_settings(self, user_email: str) -> Optional[Tuple[str, str, str, str]]:
        """Получить настройки подключения к Jira для пользователя"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Сначала пробуем найти по email
                cursor.execute('''
                    SELECT user_id, jira_username, jira_password, last_test_success
                    FROM user_jira_settings 
                    WHERE user_email = ?
                ''', (user_email,))
                result = cursor.fetchone()
                
                # Если не найден по email, пробуем найти по user_id (если email начинается с "user_")
                if not result and user_email.startswith("user_"):
                    user_id = user_email[5:]  # Убираем префикс "user_"
                    cursor.execute('''
                        SELECT user_id, jira_username, jira_password, last_test_success
                        FROM user_jira_settings 
                        WHERE user_id = ?
                    ''', (user_id,))
                    result = cursor.fetchone()
                
                if result:
                    user_id, jira_username, encrypted_password, last_test_success = result
                    
                    # Расшифровываем пароль
                    try:
                        # Проверяем, зашифрован ли пароль
                        if password_crypto.is_encrypted(encrypted_password):
                            decrypted_password = password_crypto.decrypt_password(encrypted_password)
                        else:
                            # Если пароль не зашифрован (старые данные), используем как есть
                            # но в логе отметим это
                            decrypted_password = encrypted_password
                            logger.warning(f"Пароль для {user_email} не зашифрован - требуется обновление")
                        
                        return (user_id, jira_username, decrypted_password, last_test_success)
                    
                    except Exception as decrypt_error:
                        logger.error(f"Ошибка расшифровки пароля для {user_email}: {decrypt_error}")
                        return None
                
                return None
        except Exception as e:
            logger.error(f"Ошибка получения настроек Jira для {user_email}: {e}")
            return None
    
    def update_jira_test_result(self, user_email: str, success: bool) -> bool:
        """Обновить результат тестирования подключения к Jira"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                if success:
                    # При успешном подключении сбрасываем счетчик попыток и разблокируем
                    cursor.execute('''
                        UPDATE user_jira_settings 
                        SET last_test_success = ?, last_test_at = CURRENT_TIMESTAMP,
                            connection_attempts = 0, is_blocked = 0, blocked_at = NULL,
                            last_connection_error = NULL
                        WHERE user_email = ?
                    ''', (success, user_email))
                else:
                    cursor.execute('''
                        UPDATE user_jira_settings 
                        SET last_test_success = ?, last_test_at = CURRENT_TIMESTAMP
                        WHERE user_email = ?
                    ''', (success, user_email))
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Ошибка обновления результата теста для {user_email}: {e}")
            return False
    
    def increment_connection_attempts(self, user_email: str, error_message: str = None) -> Tuple[int, bool]:
        """Увеличить счетчик попыток подключения и проверить, нужно ли заблокировать"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                # Получаем текущее количество попыток
                cursor.execute('''
                    SELECT connection_attempts, is_blocked
                    FROM user_jira_settings
                    WHERE user_email = ?
                ''', (user_email,))
                result = cursor.fetchone()
                
                if not result:
                    return 0, False
                
                current_attempts, is_blocked = result
                
                # Если уже заблокирован, не увеличиваем счетчик
                if is_blocked:
                    return current_attempts, True
                
                # Увеличиваем счетчик
                new_attempts = current_attempts + 1
                should_block = new_attempts >= 5
                
                if should_block:
                    # Блокируем пользователя
                    cursor.execute('''
                        UPDATE user_jira_settings 
                        SET connection_attempts = ?, is_blocked = 1, 
                            blocked_at = CURRENT_TIMESTAMP,
                            last_connection_error = ?
                        WHERE user_email = ?
                    ''', (new_attempts, error_message or "Превышено максимальное количество попыток", user_email))
                else:
                    # Просто увеличиваем счетчик
                    cursor.execute('''
                        UPDATE user_jira_settings 
                        SET connection_attempts = ?, last_connection_error = ?
                        WHERE user_email = ?
                    ''', (new_attempts, error_message, user_email))
                
                conn.commit()
                return new_attempts, should_block
        except Exception as e:
            logger.error(f"Ошибка обновления счетчика попыток для {user_email}: {e}")
            return 0, False
    
    def reset_connection_attempts(self, user_email: str) -> bool:
        """Сбросить счетчик попыток подключения (при смене пароля)"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE user_jira_settings 
                    SET connection_attempts = 0, is_blocked = 0, 
                        blocked_at = NULL, last_connection_error = NULL
                    WHERE user_email = ?
                ''', (user_email,))
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Ошибка сброса счетчика попыток для {user_email}: {e}")
            return False
    
    def is_user_blocked(self, user_email: str) -> bool:
        """Проверить, заблокирован ли пользователь"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT is_blocked FROM user_jira_settings WHERE user_email = ?
                ''', (user_email,))
                result = cursor.fetchone()
                return result[0] if result else False
        except Exception as e:
            logger.error(f"Ошибка проверки блокировки для {user_email}: {e}")
            return False
    
    def get_user_block_info(self, user_email: str) -> Optional[Tuple[int, bool, Optional[str]]]:
        """Получить информацию о блокировке пользователя: (попытки, заблокирован, дата блокировки)"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT connection_attempts, is_blocked, blocked_at
                    FROM user_jira_settings WHERE user_email = ?
                ''', (user_email,))
                result = cursor.fetchone()
                if result:
                    return (result[0], bool(result[1]), result[2])
                return None
        except Exception as e:
            logger.error(f"Ошибка получения информации о блокировке для {user_email}: {e}")
            return None
    
    def delete_user_jira_settings(self, user_email: str) -> bool:
        """Удалить настройки Jira пользователя"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('DELETE FROM user_jira_settings WHERE user_email = ?', (user_email,))
                conn.commit()
                if cursor.rowcount > 0:
                    logger.info(f"Настройки Jira удалены для пользователя {user_email}")
                    return True
                return False
        except Exception as e:
            logger.error(f"Ошибка удаления настроек Jira для {user_email}: {e}")
            return False
    
    def subscribe_to_project(self, project_key: str, project_name: str, channel_id: str, 
                           team_id: str, user_id: str, user_email: str) -> bool:
        """Подписать канал на мониторинг проекта"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT OR REPLACE INTO project_subscriptions 
                    (project_key, project_name, mattermost_channel_id, mattermost_team_id, 
                     subscribed_by_user_id, subscribed_by_email, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ''', (project_key, project_name, channel_id, team_id, user_id, user_email))
                conn.commit()
                logger.info(f"Канал {channel_id} подписан на проект {project_key}")
                return True
        except Exception as e:
            logger.error(f"Ошибка подписки на проект {project_key}: {e}")
            return False
    
    def unsubscribe_from_project(self, project_key: str, channel_id: str) -> bool:
        """Отписать канал от мониторинга проекта"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE project_subscriptions 
                    SET active = 0, updated_at = CURRENT_TIMESTAMP 
                    WHERE project_key = ? AND mattermost_channel_id = ?
                ''', (project_key, channel_id))
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
    
    def get_active_subscriptions(self) -> List[Tuple]:
        """Получить список активных подписок на проекты"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT project_key, project_name, mattermost_channel_id, 
                           mattermost_team_id, subscribed_by_email
                    FROM project_subscriptions 
                    WHERE active = 1
                    ORDER BY project_key
                ''')
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"Ошибка получения списка подписок: {e}")
            return []
    
    def get_subscriptions_by_channel(self, channel_id: str) -> List[Tuple]:
        """Получить подписки для конкретного канала"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT project_key, project_name, subscribed_by_email, created_at, active
                    FROM project_subscriptions 
                    WHERE mattermost_channel_id = ? AND active = 1
                    ORDER BY created_at DESC
                ''', (channel_id,))
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"Ошибка получения подписок для канала {channel_id}: {e}")
            return []
    
    def get_all_subscriptions(self) -> List[Tuple]:
        """Получить все подписки (для администраторов)"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT project_key, project_name, mattermost_channel_id, 
                           subscribed_by_email, created_at, active
                    FROM project_subscriptions 
                    ORDER BY created_at DESC
                ''')
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"Ошибка получения всех подписок: {e}")
            return []
    
    def delete_subscription_by_id(self, project_key: str, channel_id: str) -> bool:
        """Удалить конкретную подписку (для администраторов)"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    DELETE FROM project_subscriptions 
                    WHERE project_key = ? AND mattermost_channel_id = ?
                ''', (project_key, channel_id))
                conn.commit()
                if cursor.rowcount > 0:
                    logger.info(f"Подписка {project_key} в канале {channel_id} удалена")
                    return True
                return False
        except Exception as e:
            logger.error(f"Ошибка удаления подписки {project_key}/{channel_id}: {e}")
            return False
    
    def update_user_ids(self, email: str, mattermost_user_id: str = None, jira_account_id: str = None) -> bool:
        """Обновить ID пользователя в Mattermost и Jira"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                updates = []
                params = []
                
                if mattermost_user_id:
                    updates.append("mattermost_user_id = ?")
                    params.append(mattermost_user_id)
                
                if jira_account_id:
                    updates.append("jira_account_id = ?")
                    params.append(jira_account_id)
                
                if updates:
                    updates.append("updated_at = CURRENT_TIMESTAMP")
                    params.append(email)
                    
                    query = f"UPDATE monitored_users SET {', '.join(updates)} WHERE email = ?"
                    cursor.execute(query, params)
                    conn.commit()
                    return cursor.rowcount > 0
                
                return False
        except Exception as e:
            logger.error(f"Ошибка обновления пользователя {email}: {e}")
            return False
    
    def save_notification(self, project_key: str, issue_key: str, notification_type: str,
                         assignee_email: str, assignee_name: str, channel_id: str,
                         issue_summary: str, planned_hours: float, actual_hours: float,
                         due_date: str = None) -> bool:
        """Сохранить информацию об отправленном уведомлении"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT OR REPLACE INTO notification_history 
                    (project_key, issue_key, notification_type, assignee_email, assignee_name,
                     channel_id, issue_summary, planned_hours, actual_hours, due_date, notification_date)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, DATE('now'))
                ''', (project_key, issue_key, notification_type, assignee_email, assignee_name,
                      channel_id, issue_summary, planned_hours, actual_hours, due_date))
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Ошибка сохранения уведомления для {issue_key}: {e}")
            return False
    
    def update_issue_cache(self, issue_key: str, project_key: str, summary: str,
                          assignee_email: str, assignee_name: str, status: str,
                          due_date: str, original_estimate: float, time_spent: float,
                          remaining_estimate: float) -> bool:
        """Обновить кеш информации о задаче"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT OR REPLACE INTO issue_cache 
                    (issue_key, project_key, summary, assignee_email, assignee_name, status,
                     due_date, original_estimate, time_spent, remaining_estimate, last_updated)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ''', (issue_key, project_key, summary, assignee_email, assignee_name, status,
                      due_date, original_estimate, time_spent, remaining_estimate))
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Ошибка обновления кеша для задачи {issue_key}: {e}")
            return False
    
    def get_check_history(self, days: int = 7) -> List[Tuple]:
        """Получить историю проверок за последние дни"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT ch.check_date, ch.user_email, mu.name, ch.has_worklog, ch.worklog_hours
                    FROM check_history ch
                    JOIN monitored_users mu ON ch.user_email = mu.email
                    WHERE ch.check_date >= date('now', '-{} days')
                    ORDER BY ch.check_date DESC, ch.user_email
                '''.format(days))
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"Ошибка получения истории проверок: {e}")
            return []

# Глобальный экземпляр менеджера БД
db_manager = DatabaseManager()
