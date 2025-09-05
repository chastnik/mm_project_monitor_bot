"""
Клиент для работы с Mattermost API
"""
import logging
import json
import os
from typing import List, Optional, Dict
from mattermostdriver import Driver
from config import config

logger = logging.getLogger(__name__)

class MattermostClient:
    def __init__(self):
        self.driver = None
        self.bot_user_id = None
        self.bot_username = None
        self.direct_channels = {}  # Кеш DM каналов: user_id -> channel_id
        self.user_sessions_file = 'user_sessions.json'
        self.connect()
    
    def connect(self):
        """Подключение к Mattermost"""
        try:
            # Определяем схему и порт из URL
            from urllib.parse import urlparse
            parsed_url = urlparse(config.MATTERMOST_URL)
            scheme = parsed_url.scheme or 'https'
            port = parsed_url.port or (443 if scheme == 'https' else 80)
            hostname = parsed_url.hostname or parsed_url.netloc
            
            self.driver = Driver({
                'url': hostname,
                'token': config.MATTERMOST_TOKEN,
                'scheme': scheme,
                'port': port,
                'basepath': '/api/v4',
                'verify': config.MATTERMOST_SSL_VERIFY,
                'timeout': 30,
            })
            
            self.driver.login()
            
            # Получаем информацию о боте
            me = self.driver.users.get_user('me')
            self.bot_user_id = me['id']
            self.bot_username = me['username']
            
            logger.info(f"Успешно подключились к Mattermost как {me['username']}")
            
            # Инициализируем DM каналы
            self._init_direct_channels()
            
        except Exception as e:
            logger.error(f"Ошибка подключения к Mattermost: {e}")
            raise
    
    def get_user_by_email(self, email: str) -> Optional[Dict]:
        """Получить пользователя по email"""
        try:
            user = self.driver.users.get_user_by_email(email)
            return user
        except Exception as e:
            logger.warning(f"Пользователь с email {email} не найден в Mattermost: {e}")
            return None
    
    def get_users_by_emails(self, emails: List[str]) -> Dict[str, Dict]:
        """Получить пользователей по списку email"""
        users = {}
        for email in emails:
            user = self.get_user_by_email(email)
            if user:
                users[email] = user
        return users
    
    def send_channel_message(self, channel_id: str, message: str) -> bool:
        """Отправить сообщение в канал"""
        try:
            self.driver.posts.create_post({
                'channel_id': channel_id,
                'message': message
            })
            logger.info(f"Сообщение отправлено в канал {channel_id}")
            return True
        except Exception as e:
            logger.error(f"Ошибка отправки сообщения в канал: {e}")
            return False
    
    def send_direct_message(self, user_id: str, message: str) -> bool:
        """Отправить личное сообщение пользователю"""
        try:
            # Получаем или создаем DM канал
            channel_id = self._get_or_create_dm_channel(user_id)
            if not channel_id:
                logger.error(f"Не удалось создать DM канал с пользователем {user_id}")
                return False
            
            # Отправляем сообщение
            self.driver.posts.create_post({
                'channel_id': channel_id,
                'message': message
            })
            logger.info(f"Личное сообщение отправлено пользователю {user_id}")
            return True
        except Exception as e:
            logger.error(f"Ошибка отправки личного сообщения пользователю {user_id}: {e}")
            return False
    
    def send_direct_message_by_email(self, email: str, message: str) -> bool:
        """Отправить личное сообщение пользователю по email"""
        user = self.get_user_by_email(email)
        if user:
            return self.send_direct_message(user['id'], message)
        else:
            logger.warning(f"Не удалось найти пользователя с email {email}")
            return False
    
    def get_channel_info(self, channel_id: str) -> Optional[Dict]:
        """Получить информацию о канале"""
        try:
            channel = self.driver.channels.get_channel(channel_id)
            return channel
        except Exception as e:
            logger.error(f"Ошибка получения информации о канале {channel_id}: {e}")
            return None
    
    def is_user_admin(self, user_email: str) -> bool:
        """Проверить, является ли пользователь администратором"""
        return user_email.lower().strip() in [email.lower().strip() for email in config.ADMIN_EMAILS if email.strip()]
    
    def format_user_list_message(self, users_with_worklog: List[str], users_without_worklog: List[str]) -> str:
        """Форматировать сообщение со списком пользователей"""
        message_parts = []
        
        message_parts.append("📊 **Отчет о заполнении планов в Jira**")
        message_parts.append(f"Дата: {self._get_current_date()}")
        message_parts.append("")
        
        if users_with_worklog:
            message_parts.append("✅ **Заполнили планы:**")
            for user in users_with_worklog:
                message_parts.append(f"• {user}")
            message_parts.append("")
        
        if users_without_worklog:
            message_parts.append("❌ **Не заполнили планы:**")
            for user in users_without_worklog:
                message_parts.append(f"• {user}")
            message_parts.append("")
            message_parts.append("Им отправлены персональные напоминания.")
        
        if not users_with_worklog and not users_without_worklog:
            message_parts.append("ℹ️ Нет данных для отображения")
        
        return "\n".join(message_parts)
    
    def format_reminder_message(self, user_name: str = None) -> str:
        """Форматировать напоминание для пользователя"""
        greeting = f"Привет, {user_name}!" if user_name else "Привет!"
        
        return f"""{greeting}

⏰ **Напоминание о заполнении планов**

Пожалуйста, не забудь заполнить свои планы работы в Jira (плагин Tempo) за сегодня.

Это поможет команде лучше планировать работу и отслеживать прогресс проектов.

Спасибо! 🙏"""
    
    def format_plans_reminder_message(self, user_name: str = None) -> str:
        """Форматировать напоминание о планах для пользователя"""
        greeting = f"Привет, {user_name}!" if user_name else "Привет!"
        
        return f"""{greeting}

📋 **Напоминание о планировании работ**

У вас пока нет запланированных задач на сегодня в Jira.

Пожалуйста:
• Проверьте свои задачи в Jira
• Установите **Remaining Estimate** для задач, над которыми планируете работать
• Это поможет команде видеть вашу загрузку и планы

Спасибо за внимание к планированию! 📊"""
    
    def format_plans_report_message(self, users_with_plans: List[str], users_without_plans: List[str]) -> str:
        """Форматировать сообщение с отчетом о планах"""
        message_parts = []
        
        message_parts.append("📊 **Отчет о планировании работ в Jira**")
        message_parts.append(f"Дата: {self._get_current_date()}")
        message_parts.append("")
        
        if users_with_plans:
            message_parts.append("✅ **Есть планы на сегодня:**")
            for user in users_with_plans:
                message_parts.append(f"• {user}")
            message_parts.append("")
        
        if users_without_plans:
            message_parts.append("❌ **Нет запланированных задач:**")
            for user in users_without_plans:
                message_parts.append(f"• {user}")
            message_parts.append("")
            message_parts.append("Им отправлены напоминания о планировании.")
        
        if not users_with_plans and not users_without_plans:
            message_parts.append("ℹ️ Нет данных для отображения")
        
        message_parts.append("")
        message_parts.append("💡 *Планы определяются по полю Remaining Estimate в задачах Jira*")
        
        return "\n".join(message_parts)
    
    def _get_current_date(self) -> str:
        """Получить текущую дату в читаемом формате"""
        from datetime import datetime
        return datetime.now().strftime("%d.%m.%Y")
    
    def _init_direct_channels(self):
        """Инициализация существующих DM каналов"""
        try:
            # Получаем все каналы бота
            channels = self.driver.channels.get_channels_for_user(self.bot_user_id, team_id='')
            
            dm_count = 0
            for channel in channels:
                if channel['type'] == 'D':  # Direct message channel
                    # Получаем ID собеседника
                    channel_members = self.driver.channels.get_channel_members(channel['id'])
                    for member in channel_members:
                        if member['user_id'] != self.bot_user_id:
                            self.direct_channels[member['user_id']] = channel['id']
                            dm_count += 1
                            break
            
            logger.info(f"Инициализировано {dm_count} DM каналов")
            
        except Exception as e:
            logger.warning(f"Ошибка инициализации DM каналов: {e}")
    
    def _get_or_create_dm_channel(self, user_id: str) -> Optional[str]:
        """Получить или создать DM канал с пользователем"""
        try:
            # Проверяем кеш
            if user_id in self.direct_channels:
                return self.direct_channels[user_id]
            
            # Создаем новый DM канал
            direct_channel = self.driver.channels.create_direct_message_channel([self.bot_user_id, user_id])
            channel_id = direct_channel['id']
            
            # Сохраняем в кеш
            self.direct_channels[user_id] = channel_id
            
            logger.info(f"Создан новый DM канал с пользователем {user_id}: {channel_id}")
            return channel_id
            
        except Exception as e:
            logger.error(f"Ошибка создания DM канала с пользователем {user_id}: {e}")
            return None
    
    def get_direct_channel_id(self, user_id: str) -> Optional[str]:
        """Получить ID DM канала с пользователем"""
        return self.direct_channels.get(user_id)
    
    def is_direct_message(self, channel_id: str) -> bool:
        """Проверить, является ли канал личным сообщением"""
        return channel_id in self.direct_channels.values()
    
    def load_user_sessions(self) -> dict:
        """Загрузить сохраненные сессии пользователей"""
        try:
            if os.path.exists(self.user_sessions_file):
                with open(self.user_sessions_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            logger.warning(f"Ошибка загрузки сессий пользователей: {e}")
        return {}
    
    def save_user_sessions(self, sessions: dict):
        """Сохранить сессии пользователей"""
        try:
            with open(self.user_sessions_file, 'w', encoding='utf-8') as f:
                json.dump(sessions, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Ошибка сохранения сессий пользователей: {e}")
    
    def handle_new_dm_channel(self, event_data: dict):
        """Обработать создание нового DM канала"""
        try:
            channel_id = event_data.get('channel_id')
            if not channel_id:
                return
            
            # Получаем информацию о канале
            channel = self.driver.channels.get_channel(channel_id)
            if channel['type'] == 'D':
                # Получаем участников канала
                members = self.driver.channels.get_channel_members(channel_id)
                for member in members:
                    if member['user_id'] != self.bot_user_id:
                        self.direct_channels[member['user_id']] = channel_id
                        logger.info(f"Добавлен новый DM канал: {member['user_id']} -> {channel_id}")
                        break
        except Exception as e:
            logger.error(f"Ошибка обработки нового DM канала: {e}")

# Глобальный экземпляр клиента
mattermost_client = MattermostClient()
