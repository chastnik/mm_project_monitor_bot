#!/usr/bin/env python3
"""
Основной файл бота для мониторинга проектов в Jira - 
отслеживание превышения трудозатрат и просроченных сроков
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
from jira_client import jira_client
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
        self.logger.info("🚀 Запуск бота для мониторинга проектов...")
        
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
        ]
        
        # Глобальная аутентификация Jira отключена - используются только персональные настройки пользователей
        
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
        
        # Тест Jira - пропускаем, так как используются только персональные подключения
        self.logger.info("✅ Jira: настроен для персональных подключений пользователей")
        
        
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
            self.websocket = True  # Флаг успешной инициализации
            self.logger.info("✅ WebSocket настроен для получения сообщений")
            
            # Загружаем сохраненные сессии пользователей
            user_sessions = mattermost_client.load_user_sessions()
            if user_sessions:
                self.logger.info(f"Загружено {len(user_sessions)} пользовательских сессий")
            
        except Exception as e:
            self.logger.error(f"⚠️ Ошибка настройки WebSocket: {e}")
            self.logger.info("Бот будет работать без обработки команд в реальном времени")
            self.websocket = False
    
    def _websocket_handler(self, message):
        """Обработчик WebSocket сообщений"""
        try:
            event = message.get('event')
            
            # Обработка новых сообщений
            if event == 'posted':
                self._handle_posted_message(message)
            
            # Обработка создания новых каналов (включая DM)
            elif event == 'channel_created':
                mattermost_client.handle_new_dm_channel(message.get('data', {}))
            
            # Обработка добавления пользователей в каналы
            elif event == 'user_added':
                self._handle_user_added(message.get('data', {}))
                
        except Exception as e:
            self.logger.error(f"Ошибка обработки WebSocket сообщения: {e}")
    
    def _handle_posted_message(self, message):
        """Обработка новых сообщений"""
        try:
            post_data = message.get('data', {}).get('post')
            if not post_data:
                return
            
            # Безопасный парсинг JSON
            import json
            try:
                post = json.loads(post_data)
            except (json.JSONDecodeError, TypeError):
                # Fallback на eval для совместимости
                post = eval(post_data)
            
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
            team_id = message.get('data', {}).get('team_id', '')
            
            message_text = post.get('message', '').strip()
            
            # Логируем получение сообщения для отладки
            self.logger.debug(f"Получено сообщение от {user_email} в канале {channel_type}: {message_text[:50]}...")
            
            # Обрабатываем только личные сообщения или упоминания бота в каналах
            should_process = False
            
            if channel_type == 'D':  # Личные сообщения
                should_process = True
            elif f'@{mattermost_client.bot_username}' in message_text:  # Упоминания в каналах
                should_process = True
            
            if should_process and message_text:
                # Автоматически инициализируем DM канал если это первое сообщение
                if channel_type == 'D' and user_id not in mattermost_client.direct_channels:
                    mattermost_client.direct_channels[user_id] = channel_id
                    self.logger.info(f"Инициализирован новый DM канал: {user_id} -> {channel_id}")
                
                # Обрабатываем команду
                response = command_handler.handle_message(
                    message_text, user_email, channel_type, 
                    channel_id, team_id, user_id
                )
                
                if response:
                    if channel_type == 'D':
                        # Отправляем ответ в личные сообщения
                        mattermost_client.send_direct_message(user_id, response)
                    else:
                        # Отправляем ответ в канал (с упоминанием пользователя)
                        response_with_mention = f"@{user.get('username', user_email)} {response}"
                        mattermost_client.send_channel_message(channel_id, response_with_mention)
                        
        except Exception as e:
            self.logger.error(f"Ошибка обработки сообщения: {e}")
    
    def _handle_user_added(self, event_data):
        """Обработка добавления пользователей в каналы"""
        try:
            channel_id = event_data.get('channel_id')
            user_id = event_data.get('user_id')
            
            if channel_id and user_id and user_id != mattermost_client.bot_user_id:
                # Проверяем, является ли канал DM каналом
                channel = mattermost_client.driver.channels.get_channel(channel_id)
                if channel['type'] == 'D':
                    mattermost_client.direct_channels[user_id] = channel_id
                    self.logger.info(f"Добавлен пользователь в DM канал: {user_id} -> {channel_id}")
                    
        except Exception as e:
            self.logger.error(f"Ошибка обработки добавления пользователя: {e}")
    
    def _send_startup_message(self):
        """Отправить сообщение о запуске бота"""
        try:
            startup_message = f"""🤖 **Бот мониторинга проектов запущен!**

📅 **Расписание:** ежедневно в {config.CHECK_TIME}
🔍 **Активных подписок:** {len(db_manager.get_active_subscriptions())}
⚙️ **Версия:** {datetime.now().strftime('%Y.%m.%d')}

🚨 **Мониторинг:**
• Превышение трудозатрат (факт > план)
• Просроченные сроки выполнения

Используйте `subscribe PROJECT_KEY` для подписки на мониторинг проекта!"""
            
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
