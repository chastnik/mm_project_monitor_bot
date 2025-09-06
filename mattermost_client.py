"""
Упрощенный клиент для работы с Mattermost API по образцу mm_bot_summary
"""
import logging
from typing import Optional, Dict
from mattermostdriver import Driver
from config import config

logger = logging.getLogger(__name__)

class MattermostClient:
    def __init__(self):
        self.driver = None
        self.bot_user_id = None
        self.bot_username = None
        self._connect()
    
    def _connect(self):
        """Подключение к Mattermost"""
        try:
            # Простая настройка без сложных SSL конфигураций
            self.driver = Driver({
                'url': config.MATTERMOST_URL.replace('https://', '').replace('http://', ''),
                'token': config.MATTERMOST_TOKEN,
                'scheme': 'https' if 'https' in config.MATTERMOST_URL else 'http',
                'port': 443 if 'https' in config.MATTERMOST_URL else 80,
                'basepath': '/api/v4',
                'verify': config.MATTERMOST_SSL_VERIFY,
                'timeout': 30
            })
            
            self.driver.login()
            
            # Получаем информацию о боте
            me = self.driver.users.get_user('me')
            self.bot_user_id = me['id']
            self.bot_username = me['username']
            
            logger.info(f"Успешно подключились к Mattermost как {me['username']}")
            
        except Exception as e:
            logger.error(f"Ошибка подключения к Mattermost: {e}")
            raise
    
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
            # Создаем прямой канал
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
            logger.error(f"Ошибка отправки личного сообщения: {e}")
            return False
    
    def send_direct_message_by_email(self, email: str, message: str) -> bool:
        """Отправить личное сообщение пользователю по email"""
        try:
            user = self.driver.users.get_user_by_email(email)
            return self.send_direct_message(user['id'], message)
        except Exception as e:
            logger.warning(f"Не удалось отправить сообщение пользователю {email}: {e}")
            return False
    
    def get_channel_info(self, channel_id: str) -> Optional[Dict]:
        """Получить информацию о канале"""
        try:
            return self.driver.channels.get_channel(channel_id)
        except Exception as e:
            logger.error(f"Ошибка получения информации о канале {channel_id}: {e}")
            return None
    
    def get_user_by_email(self, email: str) -> Optional[Dict]:
        """Получить пользователя по email"""
        try:
            return self.driver.users.get_user_by_email(email)
        except Exception as e:
            logger.warning(f"Пользователь с email {email} не найден: {e}")
            return None
    
    def is_user_admin(self, user_email: str) -> bool:
        """Проверить, является ли пользователь администратором"""
        admin_emails = config.ADMIN_EMAILS.split(',') if config.ADMIN_EMAILS else []
        return user_email.strip() in [email.strip() for email in admin_emails]

# Глобальный экземпляр клиента (ленивая инициализация)
_mattermost_client = None

def get_mattermost_client():
    """Получить экземпляр клиента Mattermost с ленивой инициализацией"""
    global _mattermost_client
    if _mattermost_client is None:
        _mattermost_client = MattermostClient()
    return _mattermost_client

# Для обратной совместимости
mattermost_client = get_mattermost_client()
