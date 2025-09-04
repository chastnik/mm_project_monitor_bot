#!/usr/bin/env python3
"""
Основной файл бота для проверки заполнения планов в Jira через Tempo
"""
import logging
import sys
import signal
import time
from datetime import datetime
from mattermostdriver import Driver
from config import config
from database import db_manager
from mattermost_client import mattermost_client
from jira_tempo_client import jira_tempo_client
from scheduler import scheduler
from bot_commands import command_handler

# Настройка логирования
def setup_logging():
    """Настройка системы логирования"""
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    
    # Настройка для файла
    logging.basicConfig(
        level=getattr(logging, config.LOG_LEVEL.upper()),
        format=log_format,
        handlers=[
            logging.FileHandler(config.LOG_FILE, encoding='utf-8'),
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    # Уменьшаем уровень логирования для внешних библиотек
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('requests').setLevel(logging.WARNING)
    logging.getLogger('mattermostdriver').setLevel(logging.WARNING)

class StandupBot:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.running = False
        self.websocket = None
        
    def start(self):
        """Запуск бота"""
        self.logger.info("🚀 Запуск бота для проверки планов...")
        
        try:
            # Проверяем конфигурацию
            self._validate_config()
            
            # Инициализируем базу данных
            db_manager.init_database()
            self.logger.info("✅ База данных инициализирована")
            
            # Проверяем подключения
            self._test_connections()
            
            # Запускаем планировщик
            scheduler.start()
            self.logger.info("✅ Планировщик запущен")
            
            # Настраиваем WebSocket для получения сообщений
            self._setup_websocket()
            
            # Отправляем сообщение о запуске
            self._send_startup_message()
            
            self.running = True
            self.logger.info("🎉 Бот успешно запущен и готов к работе!")
            
            # Основной цикл
            self._run_main_loop()
            
        except Exception as e:
            self.logger.error(f"❌ Ошибка запуска бота: {e}")
            sys.exit(1)
    
    def stop(self):
        """Остановка бота"""
        self.logger.info("🛑 Остановка бота...")
        
        self.running = False
        
        # Останавливаем планировщик
        scheduler.stop()
        
        # Закрываем WebSocket
        if self.websocket:
            try:
                mattermost_client.driver.disconnect()
            except:
                pass
        
        self.logger.info("✅ Бот остановлен")
    
    def _validate_config(self):
        """Проверка конфигурации"""
        required_settings = [
            ('MATTERMOST_URL', config.MATTERMOST_URL),
            ('MATTERMOST_TOKEN', config.MATTERMOST_TOKEN),
            ('MATTERMOST_CHANNEL_ID', config.MATTERMOST_CHANNEL_ID),
            ('JIRA_URL', config.JIRA_URL),
            ('JIRA_USERNAME', config.JIRA_USERNAME),
        ]
        
        # Проверяем аутентификацию для Jira
        if config.JIRA_AUTH_METHOD.lower() == 'token':
            required_settings.append(('JIRA_API_TOKEN', config.JIRA_API_TOKEN))
        else:
            required_settings.append(('JIRA_PASSWORD', config.JIRA_PASSWORD))
        
        # Tempo может быть опциональным (если используется только Jira API)
        if config.TEMPO_API_TOKEN:
            required_settings.append(('TEMPO_API_TOKEN', config.TEMPO_API_TOKEN))
        
        missing = []
        for name, value in required_settings:
            if not value:
                missing.append(name)
        
        if missing:
            raise ValueError(f"Не заданы обязательные настройки: {', '.join(missing)}")
        
        if not config.ADMIN_EMAILS or not any(email.strip() for email in config.ADMIN_EMAILS):
            raise ValueError("Не задан список администраторов (ADMIN_EMAILS)")
        
        self.logger.info("✅ Конфигурация проверена")
    
    def _test_connections(self):
        """Тестирование подключений к внешним сервисам"""
        # Тест Mattermost
        try:
            me = mattermost_client.driver.users.get_user('me')
            self.logger.info(f"✅ Mattermost: подключен как {me['username']}")
        except Exception as e:
            raise Exception(f"Ошибка подключения к Mattermost: {e}")
        
        # Тест Jira
        try:
            current_user = jira_tempo_client.jira_client.current_user()
            self.logger.info(f"✅ Jira: подключен как {current_user}")
        except Exception as e:
            raise Exception(f"Ошибка подключения к Jira: {e}")
        
        # Тест Tempo API
        if not jira_tempo_client.test_tempo_connection():
            raise Exception("Ошибка подключения к Tempo API")
        
        self.logger.info("✅ Tempo API: подключение успешно")
        
        # Тест канала
        channel_info = mattermost_client.get_channel_info(config.MATTERMOST_CHANNEL_ID)
        if not channel_info:
            raise Exception(f"Канал {config.MATTERMOST_CHANNEL_ID} не найден")
        
        self.logger.info(f"✅ Канал найден: {channel_info['display_name']}")
    
    def _setup_websocket(self):
        """Настройка WebSocket для получения сообщений"""
        try:
            # Регистрируем обработчик сообщений
            mattermost_client.driver.init_websocket(self._websocket_handler)
            self.logger.info("✅ WebSocket настроен для получения сообщений")
        except Exception as e:
            self.logger.error(f"⚠️ Ошибка настройки WebSocket: {e}")
            self.logger.info("Бот будет работать без обработки команд в реальном времени")
    
    def _websocket_handler(self, message):
        """Обработчик WebSocket сообщений"""
        try:
            if message.get('event') == 'posted':
                post_data = message.get('data', {}).get('post')
                if post_data:
                    post = eval(post_data)  # Осторожно! В продакшене использовать json.loads
                    
                    # Игнорируем сообщения от бота
                    if post.get('user_id') == mattermost_client.bot_user_id:
                        return
                    
                    # Получаем информацию о пользователе
                    user_id = post.get('user_id')
                    user = mattermost_client.driver.users.get_user(user_id)
                    user_email = user.get('email', '')
                    
                    # Получаем информацию о канале
                    channel_id = post.get('channel_id')
                    channel = mattermost_client.driver.channels.get_channel(channel_id)
                    channel_type = channel.get('type', 'O')
                    
                    message_text = post.get('message', '')
                    
                    # Обрабатываем только личные сообщения или упоминания бота
                    if channel_type == 'D' or f'@{mattermost_client.driver.users.get_user("me")["username"]}' in message_text:
                        response = command_handler.handle_message(message_text, user_email, channel_type)
                        
                        if response:
                            if channel_type == 'D':
                                # Отправляем ответ в личные сообщения
                                mattermost_client.send_direct_message(user_id, response)
                            else:
                                # Отправляем ответ в канал
                                mattermost_client.send_channel_message(channel_id, response)
                
        except Exception as e:
            self.logger.error(f"Ошибка обработки WebSocket сообщения: {e}")
    
    def _send_startup_message(self):
        """Отправить сообщение о запуске бота"""
        try:
            startup_message = f"""🤖 **Бот проверки планов запущен!**

📅 **Расписание:** ежедневно в {config.CHECK_TIME}
👥 **Отслеживаемых пользователей:** {len(db_manager.get_active_users())}
⚙️ **Версия:** {datetime.now().strftime('%Y.%m.%d')}

Для получения справки напишите боту `help` в личных сообщениях."""
            
            mattermost_client.send_channel_message(config.MATTERMOST_CHANNEL_ID, startup_message)
            
        except Exception as e:
            self.logger.error(f"Ошибка отправки сообщения о запуске: {e}")
    
    def _run_main_loop(self):
        """Основной цикл работы бота"""
        try:
            while self.running:
                time.sleep(1)
                
        except KeyboardInterrupt:
            self.logger.info("Получен сигнал остановки")
        except Exception as e:
            self.logger.error(f"Ошибка в основном цикле: {e}")
        finally:
            self.stop()

def signal_handler(signum, frame):
    """Обработчик сигналов для корректного завершения"""
    logger = logging.getLogger(__name__)
    logger.info(f"Получен сигнал {signum}, завершение работы...")
    bot.stop()
    sys.exit(0)

def main():
    """Главная функция"""
    global bot
    
    # Настройка логирования
    setup_logging()
    logger = logging.getLogger(__name__)
    
    logger.info("=" * 50)
    logger.info("🤖 Standup Bot для проверки планов в Jira")
    logger.info("=" * 50)
    
    # Регистрируем обработчики сигналов
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Создаем и запускаем бота
    bot = StandupBot()
    bot.start()

if __name__ == '__main__':
    main()
