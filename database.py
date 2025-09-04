"""
Модуль для работы с базой данных SQLite
"""
import sqlite3
import logging
from typing import List, Optional, Tuple
from config import config

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
                
                # Таблица пользователей для мониторинга
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS monitored_users (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        email TEXT UNIQUE NOT NULL,
                        name TEXT,
                        mattermost_user_id TEXT,
                        jira_account_id TEXT,
                        active BOOLEAN DEFAULT 1,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # Таблица для истории проверок
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS check_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        check_date DATE NOT NULL,
                        user_email TEXT NOT NULL,
                        has_worklog BOOLEAN NOT NULL,
                        worklog_hours REAL DEFAULT 0,
                        notified BOOLEAN DEFAULT 0,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_email) REFERENCES monitored_users (email)
                    )
                ''')
                
                # Индексы для оптимизации
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_email ON monitored_users(email)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_check_date ON check_history(check_date)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_check ON check_history(user_email, check_date)')
                
                conn.commit()
                logger.info("База данных инициализирована успешно")
                
        except Exception as e:
            logger.error(f"Ошибка инициализации базы данных: {e}")
            raise
    
    def add_user(self, email: str, name: str = None, mattermost_user_id: str = None, jira_account_id: str = None) -> bool:
        """Добавить пользователя в список мониторинга"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO monitored_users (email, name, mattermost_user_id, jira_account_id)
                    VALUES (?, ?, ?, ?)
                ''', (email, name, mattermost_user_id, jira_account_id))
                conn.commit()
                logger.info(f"Пользователь {email} добавлен в мониторинг")
                return True
        except sqlite3.IntegrityError:
            logger.warning(f"Пользователь {email} уже существует в базе")
            return False
        except Exception as e:
            logger.error(f"Ошибка добавления пользователя {email}: {e}")
            return False
    
    def remove_user(self, email: str) -> bool:
        """Удалить пользователя из списка мониторинга"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('UPDATE monitored_users SET active = 0 WHERE email = ?', (email,))
                if cursor.rowcount > 0:
                    conn.commit()
                    logger.info(f"Пользователь {email} деактивирован")
                    return True
                else:
                    logger.warning(f"Пользователь {email} не найден")
                    return False
        except Exception as e:
            logger.error(f"Ошибка удаления пользователя {email}: {e}")
            return False
    
    def get_active_users(self) -> List[Tuple]:
        """Получить список активных пользователей"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT email, name, mattermost_user_id, jira_account_id
                    FROM monitored_users 
                    WHERE active = 1
                    ORDER BY email
                ''')
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"Ошибка получения списка пользователей: {e}")
            return []
    
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
    
    def save_check_result(self, user_email: str, check_date: str, has_worklog: bool, worklog_hours: float = 0) -> bool:
        """Сохранить результат проверки"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT OR REPLACE INTO check_history 
                    (user_email, check_date, has_worklog, worklog_hours)
                    VALUES (?, ?, ?, ?)
                ''', (user_email, check_date, has_worklog, worklog_hours))
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Ошибка сохранения результата проверки для {user_email}: {e}")
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
