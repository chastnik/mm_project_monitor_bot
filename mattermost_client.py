"""
Клиент для работы с Mattermost API
"""
import logging
from typing import List, Optional, Dict
from mattermostdriver import Driver
from config import config

logger = logging.getLogger(__name__)

class MattermostClient:
    def __init__(self):
        self.driver = None
        self.bot_user_id = None
        self.connect()
    
    def connect(self):
        """Подключение к Mattermost"""
        try:
            self.driver = Driver({
                'url': config.MATTERMOST_URL,
                'token': config.MATTERMOST_TOKEN,
                'scheme': 'https',
                'port': 443,
                'basepath': '/api/v4',
                'verify': True,
                'timeout': 30,
            })
            
            self.driver.login()
            
            # Получаем информацию о боте
            me = self.driver.users.get_user('me')
            self.bot_user_id = me['id']
            
            logger.info(f"Успешно подключились к Mattermost как {me['username']}")
            
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
            # Создаем или получаем прямой канал
            direct_channel = self.driver.channels.create_direct_message_channel([self.bot_user_id, user_id])
            channel_id = direct_channel['id']
            
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
    
    def _get_current_date(self) -> str:
        """Получить текущую дату в читаемом формате"""
        from datetime import datetime
        return datetime.now().strftime("%d.%m.%Y")

# Глобальный экземпляр клиента
mattermost_client = MattermostClient()
