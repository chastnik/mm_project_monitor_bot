"""
Упрощенный клиент для работы с Mattermost API по образцу mm_bot_summary
"""
import logging
import re
import asyncio
import json
import websockets
import ssl
import time
from typing import Optional, Dict, Any
from urllib.parse import urlparse
from mattermostdriver import Driver
from config import config

logger = logging.getLogger(__name__)

class MattermostClient:
    def __init__(self):
        self.driver = None
        self.bot_user_id = None
        self.bot_username = None
        self._running = False
        self._websocket = None
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

    def upload_image(self, channel_id: str, file_path: str, message: str = "", root_id: str = None) -> bool:
        """Загрузить изображение в канал и опубликовать пост с файлом"""
        try:
            import os
            filename = file_path.split('/')[-1]
            if not os.path.exists(file_path):
                logger.error(f"Файл для загрузки не найден: {file_path}")
                return False
            with open(file_path, 'rb') as f:
                data = f.read()

            # Пробуем разные варианты параметров в зависимости от версии драйвера
            upload_result = None
            try:
                upload_result = self.driver.files.upload_file(
                    channel_id=channel_id,
                    files={'files': (filename, data)}
                )
            except Exception as e1:
                logger.warning(f"upload_file(variant1) ошибка: {e1}")
                try:
                    upload_result = self.driver.files.upload_file(
                        channel_id=channel_id,
                        files={'files': (filename, data, 'image/jpeg')}
                    )
                except Exception as e2:
                    logger.error(f"upload_file(variant2) ошибка: {e2}")
                    return False

            file_ids = []
            if isinstance(upload_result, dict):
                # Новые версии возвращают объект с file_infos
                if 'file_infos' in upload_result and upload_result['file_infos']:
                    file_ids = [fi['id'] for fi in upload_result['file_infos']]
                # Старые версии могли возвращать file_id напрямую
                if 'id' in upload_result:
                    file_ids.append(upload_result['id'])
            else:
                logger.warning(f"Неизвестный формат ответа upload_file: {type(upload_result)}")

            if not file_ids:
                logger.error("Не удалось получить file_ids после загрузки изображения")
                return False

            post_data = {
                'channel_id': channel_id,
                'message': message or '',
                'file_ids': file_ids
            }
            if root_id:
                post_data['root_id'] = root_id

            self.driver.posts.create_post(post_data)
            logger.info(f"Изображение {filename} отправлено в канал {channel_id}")
            return True
        except Exception as e:
            logger.error(f"Ошибка загрузки изображения в канал {channel_id}: {e}")
            return False
    
    def is_user_admin(self, user_email: str) -> bool:
        """Проверить, является ли пользователь администратором"""
        admin_emails = config.ADMIN_EMAILS if config.ADMIN_EMAILS else []
        return user_email.strip() in [email.strip() for email in admin_emails]
    
    def start_listening(self):
        """Запуск прослушивания WebSocket сообщений"""
        if not self.driver:
            logger.error("❌ Драйвер Mattermost не инициализирован")
            return
        
        self._running = True
        logger.info("🎧 Начинаю прослушивание событий WebSocket...")
        
        # Основной цикл переподключения
        while self._running:
            try:
                asyncio.run(self._connect_websocket())
            except Exception as e:
                logger.error(f"❌ Ошибка WebSocket соединения: {e}")
                if self._running:
                    logger.info("🔄 Переподключение через 5 секунд...")
                    time.sleep(5)
    
    async def _connect_websocket(self):
        """Подключение к WebSocket"""
        # Парсим URL для WebSocket
        parsed_url = urlparse(config.MATTERMOST_URL)
        
        # Определяем схему WebSocket
        ws_scheme = 'wss' if parsed_url.scheme == 'https' else 'ws'
        ws_port = parsed_url.port or (443 if parsed_url.scheme == 'https' else 80)
        
        ws_url = f"{ws_scheme}://{parsed_url.hostname}:{ws_port}/api/v4/websocket"
        
        logger.info(f"🔌 Подключение к WebSocket: {ws_url}")
        
        # Настройка SSL контекста
        ssl_context = None
        if ws_scheme == 'wss':
            ssl_context = ssl.create_default_context()
            # Для разработки можно отключить проверку сертификатов
            if not config.MATTERMOST_SSL_VERIFY:
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE
        
        try:
            # Подключение к WebSocket
            async with websockets.connect(
                ws_url,
                ssl=ssl_context,
                ping_interval=30,
                ping_timeout=10,
                close_timeout=10
            ) as websocket:
                self._websocket = websocket
                
                # Аутентификация
                await self._authenticate_websocket()
                
                logger.info("✅ WebSocket подключен и аутентифицирован")
                
                # Основной цикл обработки сообщений
                async for message in websocket:
                    if not self._running:
                        break
                    # Обрабатываем разные типы сообщений WebSocket
                    if isinstance(message, bytes):
                        message_str = message.decode()
                    else:
                        message_str = str(message)
                    await self._handle_websocket_message(message_str)
                    
        except websockets.exceptions.ConnectionClosed:
            logger.warning("⚠️ WebSocket соединение закрыто")
        except Exception as e:
            logger.error(f"❌ Ошибка WebSocket: {e}")
            raise
    
    async def _authenticate_websocket(self):
        """Аутентификация WebSocket соединения"""
        if self._websocket is None:
            raise Exception("WebSocket соединение не установлено")
            
        auth_message = {
            "seq": 1,
            "action": "authentication_challenge",
            "data": {
                "token": config.MATTERMOST_TOKEN
            }
        }
        
        await self._websocket.send(json.dumps(auth_message))
        
        # Ждем подтверждения аутентификации
        auth_timeout = 10
        start_time = time.time()
        
        while time.time() - start_time < auth_timeout:
            try:
                message = await asyncio.wait_for(self._websocket.recv(), timeout=1.0)
                event = json.loads(message)
                
                if event.get('event') == 'hello':
                    logger.info("✅ WebSocket аутентификация успешна")
                    return
                    
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"❌ Ошибка аутентификации WebSocket: {e}")
                raise
        
        raise Exception("Таймаут аутентификации WebSocket")
    
    async def _handle_websocket_message(self, message: str):
        """Обработка сообщения от WebSocket"""
        try:
            event = json.loads(message)
            event_type = event.get('event')
            
            # Обрабатываем различные типы событий
            if event_type == 'posted':
                await self._handle_post_event(event)
            elif event_type == 'hello':
                logger.debug("💬 Получен hello от WebSocket")
            else:
                logger.debug(f"💬 Событие WebSocket: {event_type}")
                
        except json.JSONDecodeError as e:
            logger.error(f"❌ Ошибка парсинга JSON от WebSocket: {e}")
        except Exception as e:
            logger.error(f"❌ Ошибка обработки WebSocket сообщения: {e}")
    
    async def _handle_post_event(self, event: Dict[str, Any]):
        """Обработка события нового поста"""
        try:
            # Извлекаем данные поста
            post_data = event.get('data', {}).get('post')
            if not post_data:
                return
            
            # Парсим пост (может быть строкой JSON)
            if isinstance(post_data, str):
                post = json.loads(post_data)
            else:
                post = post_data
            
            # Игнорируем сообщения от самого бота
            if post.get('user_id') == self.bot_user_id:
                return
            
            message = post.get('message', '').strip()
            channel_id = post.get('channel_id')
            post_id = post.get('id')
            user_id = post.get('user_id')
            root_id = post.get('root_id') or post_id  # ID треда или самого поста
            
            # Проверяем, является ли это личным сообщением
            if self._is_direct_message(channel_id):
                await self._handle_direct_message(channel_id, message, user_id)
                return
            
            # В каналах обрабатываем только команды с упоминанием бота
            if self._is_bot_mentioned(message):
                logger.info(f"📝 Получена команда с упоминанием бота в канале {channel_id}")
                await self._handle_bot_mention_command(channel_id, message, user_id, root_id, post_id)
                return
                
        except Exception as e:
            logger.error(f"❌ Ошибка обработки события поста: {e}")
    
    def _is_direct_message(self, channel_id: str) -> bool:
        """Проверяет, является ли канал личным сообщением"""
        try:
            # Получаем информацию о канале
            channel_info = self.driver.channels.get_channel(channel_id)
            return channel_info.get('type') == 'D'  # D = Direct message
        except:
            return False
    
    def _is_bot_mentioned(self, message: str) -> bool:
        """Проверяет, упоминается ли бот в сообщении"""
        if not self.bot_username:
            return False
        
        # Проверяем упоминания через @username
        mention_patterns = [
            f'@{self.bot_username}',
            f'@jora',  # Имя из конфигурации
            f'@Жора',  # Отображаемое имя в канале
            f'@project-monitor-bot',  # Полное имя
            f'@project_monitor_bot',  # Альтернативное имя
            f'@ask',   # Тестовый бот
        ]
        
        message_lower = message.lower()
        # Проверяем точные упоминания и частичные совпадения
        for pattern in mention_patterns:
            if pattern.lower() in message_lower:
                logger.info(f"🔍 Найдено упоминание бота: '{pattern}' в сообщении: '{message}'")
                return True
        
        # Дополнительная проверка: ищем любые упоминания @username
        import re
        mentions = re.findall(r'@(\w+)', message)
        for mention in mentions:
            if mention.lower() in ['jora', 'жора', 'ask', self.bot_username.lower()]:
                logger.info(f"🔍 Найдено упоминание через regex: '@{mention}' в сообщении: '{message}'")
                return True
        
        return False
    
    def _is_command(self, message: str) -> bool:
        """Проверяет, является ли сообщение командой"""
        message_lower = message.lower().strip()
        
        # Расширенный список команд с алиасами
        command_aliases = {
            'help': ['help', 'справка', 'помощь', 'хелп', 'команды', 'что умеешь'],
            'subscribe': ['subscribe', 'подписка', 'подпиши', 'подпиши на проект', 'проект', 'мониторить', 'отслеживать'],
            'unsubscribe': ['unsubscribe', 'отписка', 'отпиши', 'отпиши от проекта', 'не мониторить', 'не отслеживать'],
            'list_subscriptions': ['list_subscriptions', 'подписки', 'список подписок', 'мои подписки', 'что отслеживаешь'],
            'run_subscriptions': ['run_subscriptions', 'проверь', 'проверь подписки', 'запусти проверку', 'мониторинг'],
            'list_projects': ['list_projects', 'проекты', 'список проектов', 'все проекты', 'доступные проекты', 'показать проекты', 'какие проекты'],
            'setup_jira': ['setup_jira', 'настрой jira', 'настрой подключение', 'jira настройка', 'настрой джира', 'настрой джиру'],
            'test_jira': ['test_jira', 'проверь jira', 'тест jira', 'проверь подключение'],
            'change_password': ['change_password', 'смени пароль', 'измени пароль', 'новый пароль'],
            'history': ['history', 'история', 'история уведомлений', 'что было'],
            'status': ['status', 'статус', 'как дела', 'что происходит'],
            'analytics': ['analytics', 'аналитика', 'аналитика проекта', 'покажи аналитику']
        }
        
        # Проверяем все алиасы команд
        for command, aliases in command_aliases.items():
            if any(alias in message_lower for alias in aliases):
                return True
        
        return False
    
    def _get_main_command(self, message: str) -> str:
        """Получить основную команду из алиаса"""
        message_lower = message.lower().strip()
        
        command_aliases = {
            'help': ['help', 'справка', 'помощь', 'хелп', 'команды', 'что умеешь'],
            'subscribe': ['subscribe', 'подписка', 'подпиши', 'подпиши на проект', 'проект', 'мониторить', 'отслеживать'],
            'unsubscribe': ['unsubscribe', 'отписка', 'отпиши', 'отпиши от проекта', 'не мониторить', 'не отслеживать'],
            'list_subscriptions': ['list_subscriptions', 'подписки', 'список подписок', 'мои подписки', 'что отслеживаешь'],
            'run_subscriptions': ['run_subscriptions', 'проверь', 'проверь подписки', 'запусти проверку', 'мониторинг'],
            'list_projects': ['list_projects', 'проекты', 'список проектов', 'все проекты', 'доступные проекты', 'показать проекты', 'какие проекты'],
            'setup_jira': ['setup_jira', 'настрой jira', 'настрой подключение', 'jira настройка', 'настрой джира', 'настрой джиру'],
            'test_jira': ['test_jira', 'проверь jira', 'тест jira', 'проверь подключение'],
            'change_password': ['change_password', 'смени пароль', 'измени пароль', 'новый пароль'],
            'history': ['history', 'история', 'история уведомлений', 'что было'],
            'status': ['status', 'статус', 'как дела', 'что происходит'],
            'analytics': ['analytics', 'аналитика', 'аналитика проекта', 'покажи аналитику']
        }
        
        for command, aliases in command_aliases.items():
            if any(alias in message_lower for alias in aliases):
                return command
        
        return 'unknown'
    
    async def _handle_direct_message(self, channel_id: str, message: str, user_id: str):
        """Обработка личных сообщений"""
        try:
            # Получаем информацию о пользователе
            user = self.driver.users.get_user(user_id)
            username = user.get('username', 'Неизвестный')
            
            logger.info(f"📨 Получено личное сообщение от {username}: {message}")
            
            # Обрабатываем команды
            if self._is_command(message):
                await self._handle_command(channel_id, message, user_id, username)
            else:
                # Для любого другого сообщения отправляем справку с подсказками
                await self._send_help_with_suggestions(channel_id, message)
            
        except Exception as e:
            logger.error(f"❌ Ошибка обработки личного сообщения: {e}")
    
    async def _handle_bot_mention_command(self, channel_id: str, message: str, user_id: str, root_id: str, post_id: str):
        """Обработка команд с упоминанием бота"""
        try:
            # Получаем информацию о пользователе
            user = self.driver.users.get_user(user_id)
            username = user.get('username', 'Неизвестный')
            
            # Удаляем упоминание бота из сообщения
            cleaned_message = self._remove_bot_mention(message)
            
            # Обрабатываем команду
            await self._handle_command(channel_id, cleaned_message, user_id, username, root_id)
                
        except Exception as e:
            logger.error(f"❌ Ошибка обработки команды с упоминанием бота: {e}")
    
    async def _handle_channel_command(self, channel_id: str, message: str, user_id: str, root_id: str, post_id: str):
        """Обработка команд в канале"""
        try:
            # Получаем информацию о пользователе
            user = self.driver.users.get_user(user_id)
            username = user.get('username', 'Неизвестный')
            
            # Обрабатываем команду
            await self._handle_command(channel_id, message, user_id, username, root_id)
                
        except Exception as e:
            logger.error(f"❌ Ошибка обработки команды в канале: {e}")
    
    def _remove_bot_mention(self, message: str) -> str:
        """Убирает упоминание бота из сообщения"""
        if not self.bot_username:
            return message
        
        # Паттерны для удаления упоминаний
        mention_patterns = [
            f'@{self.bot_username}',
            '@jora',
            '@Жора',
            '@project-monitor-bot',
            '@project_monitor_bot'
        ]
        
        cleaned = message
        for pattern in mention_patterns:
            cleaned = cleaned.replace(pattern, '')
        
        return cleaned.strip()
    
    async def _handle_command(self, channel_id: str, message: str, user_id: str, username: str, root_id: str = None):
        """Обработка команд"""
        try:
            from bot_commands import command_handler
            
            # Получаем email пользователя
            user = self.driver.users.get_user(user_id)
            user_email = user.get('email', username)  # Используем email или username как fallback
            
            # Определяем тип канала
            channel_type = 'D' if self._is_direct_message(channel_id) else 'O'
            
            # Получаем основную команду из алиаса
            main_command = self._get_main_command(message)
            
            # Если команда не распознана, отправляем подсказки
            if main_command == 'unknown':
                await self._send_help_with_suggestions(channel_id, message)
                return
            
            # Отладочная информация
            logger.info(f"🔍 Отладка: message={message}, type={type(message)}")
            
            # Обрабатываем команду
            response = command_handler.handle_message(
                message, user_email, channel_type, channel_id, None, user_id
            )
            
            # Отладочная информация о ответе команды
            logger.info(f"🔍 Ответ команды: {response}, тип: {type(response)}")
            
            if response:
                # Отправляем ответ
                if root_id:
                    # Ответ в тред
                    self.driver.posts.create_post({
                        'channel_id': channel_id,
                        'message': response,
                        'root_id': root_id
                    })
                else:
                    # Обычное сообщение
                    self.driver.posts.create_post({
                        'channel_id': channel_id,
                        'message': response
                    })
                
                logger.info(f"✅ Ответ отправлен пользователю {username}")
            
        except Exception as e:
            logger.error(f"❌ Ошибка обработки команды: {e}")
    
    async def _send_help_message(self, channel_id: str):
        """Отправка справочного сообщения: различаем ЛС и каналы"""
        try:
            is_dm = self._is_direct_message(channel_id)
            if is_dm:
                help_message = f"""
🤖 **Привет! Я Project Monitor Bot**

Я помогаю мониторить проекты в Jira и отслеживать превышение трудозатрат и просроченные сроки.

**Основные команды (личные сообщения):**
• `help` / `справка` / `помощь` - показать эту справку
• `setup_jira username password` / `настрой jira username password` / `настрой джира username password` / `настрой джиру username password` - настроить подключение к Jira
• `test_jira` / `проверь jira` / `тест jira` - проверить подключение к Jira
• `list_projects` / `проекты` / `список проектов` - показать все доступные проекты в Jira

**Для начала работы:**
1. Настройте подключение к Jira: `setup_jira your_username your_password`
2. Проверьте подключение: `test_jira`
3. В канале подпишитесь на проект: `@{self.bot_username} subscribe PROJECT_KEY`

**Безопасность:** Все пароли шифруются AES-256 + PBKDF2HMAC
"""
            else:
                help_message = f"""
🤖 **Привет! Я Project Monitor Bot**

Я помогаю мониторить проекты в Jira и отслеживать превышение трудозатрат и просроченные сроки.

**Основные команды (в каналах с упоминанием бота):**
• `@{self.bot_username} help` / `@{self.bot_username} справка`
• `@{self.bot_username} setup_jira username password` / `@{self.bot_username} настрой jira username password`
• `@{self.bot_username} test_jira` / `@{self.bot_username} проверь jira`
• `@{self.bot_username} list_projects` / `@{self.bot_username} проекты`
• `@{self.bot_username} subscribe PROJECT_KEY` / `@{self.bot_username} подпиши на проект PROJECT_KEY`
• `@{self.bot_username} list_subscriptions` / `@{self.bot_username} подписки`
• `@{self.bot_username} run_subscriptions` / `@{self.bot_username} проверь подписки`

**Для начала работы:**
1. **Добавьте бота в канал** (если еще не добавлен)
2. Настройте подключение к Jira в ЛС: `setup_jira your_username your_password`
3. Проверьте подключение: `test_jira`
4. В канале подпишитесь на проект: `@{self.bot_username} subscribe PROJECT_KEY`

**⚠️ Важно:** 
• В каналах команды работают только с упоминанием бота: `@{self.bot_username} команда`
• Бот должен быть добавлен в канал перед выполнением команд

**Примеры команд в канале:**
• `@{self.bot_username} подпиши на проект IDB`
• `@{self.bot_username} проверь подписки`
• `@{self.bot_username} подписки`

**Безопасность:** Все пароли шифруются AES-256 + PBKDF2HMAC
"""
            
            self.driver.posts.create_post({
                'channel_id': channel_id,
                'message': help_message
            })
            
        except Exception as e:
            logger.error(f"❌ Ошибка отправки справки: {e}")
    
    async def _send_help_with_suggestions(self, channel_id: str, message: str):
        """Отправка справки с подсказками по командам"""
        try:
            # Анализируем сообщение для подсказок
            message_lower = message.lower().strip()
            suggestions = []
            
            # Подсказки на основе ключевых слов (адаптация под DM/канал)
            is_dm = self._is_direct_message(channel_id)
            prefix = '' if is_dm else f'@{self.bot_username} '
            if any(word in message_lower for word in ['подписк', 'проект', 'монитор', 'отслеж']):
                suggestions.append(f"💡 Попробуйте: `{prefix}подпиши на проект IDB` или `{prefix}subscribe IDB`")
            elif any(word in message_lower for word in ['jira', 'настрой', 'подключ', 'джира', 'джиру']):
                suggestions.append(f"💡 Попробуйте: `{prefix}настрой jira username password` или `{prefix}setup_jira username password`")
            elif any(word in message_lower for word in ['провер', 'тест', 'статус']):
                suggestions.append(f"💡 Попробуйте: `{prefix}проверь jira` или `{prefix}test_jira`")
            elif any(word in message_lower for word in ['список', 'подписк', 'что']):
                suggestions.append(f"💡 Попробуйте: `{prefix}подписки` или `{prefix}list_subscriptions`")
            elif any(word in message_lower for word in ['проект', 'доступн', 'какие', 'показать']):
                suggestions.append(f"💡 Попробуйте: `{prefix}проекты` или `{prefix}list_projects` для просмотра всех проектов")
            else:
                suggestions.append(f"💡 Попробуйте: `{prefix}проекты` для просмотра всех доступных проектов")
                suggestions.append(f"💡 Или: `{prefix}подпиши на проект IDB` для подписки на проект")
                suggestions.append(f"💡 Или: `{prefix}настрой jira username password` для настройки Jira")
            
            help_message = f"""
🤖 **Привет! Я Project Monitor Bot**

Я не понял вашу команду: `{message}`

**Основные команды:**
• `{prefix}проекты` - показать все доступные проекты в Jira
• `{prefix}подпиши на проект IDB` - подписка на мониторинг проекта
• `{prefix}настрой jira username password` - настройка подключения к Jira
• `{prefix}проверь jira` - проверка подключения к Jira
• `{prefix}подписки` - показать активные подписки
• `{prefix}проверь подписки` - запустить проверку подписок

**Подсказки:**
{chr(10).join(suggestions)}

**Для полной справки:** `@Jora help`
"""
            
            self.driver.posts.create_post({
                'channel_id': channel_id,
                'message': help_message
            })
            
        except Exception as e:
            logger.error(f"❌ Ошибка отправки справки с подсказками: {e}")
    
    def stop(self):
        """Остановка клиента"""
        logger.info("🛑 Остановка Mattermost клиента...")
        self._running = False
        
        if self._websocket:
            try:
                asyncio.create_task(self._websocket.close())
            except:
                pass
        
        logger.info("✅ Mattermost клиент остановлен")

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