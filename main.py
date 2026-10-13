#!/usr/bin/env python3
"""
Основной файл бота для мониторинга проектов в Jira -
отслеживание превышения трудозатрат и просроченных сроков
"""

import contextlib
import logging
import signal
import sys
import time
from datetime import datetime

from auth_messages import legacy_user_disabled_message
from config import config
from database import db_manager
from mattermost_client import mattermost_client
from scheduler import scheduler


# Настройка логирования
def setup_logging():
    """Настройка системы логирования"""
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    # Настройка для файла
    logging.basicConfig(
        level=getattr(logging, config.LOG_LEVEL.upper()),
        format=log_format,
        handlers=[logging.FileHandler(config.LOG_FILE, encoding="utf-8"), logging.StreamHandler(sys.stdout)],
    )

    # Уменьшаем уровень логирования для внешних библиотек
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)
    logging.getLogger("mattermostdriver").setLevel(logging.WARNING)


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

            # Отключаем пользователей со входом по логину/паролю и просим войти по PAT
            self._notify_legacy_users()

            # Отправляем сообщение о запуске
            self._send_startup_message()

            # Информация о режиме работы
            self._send_mode_info()

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
            with contextlib.suppress(Exception):
                mattermost_client.driver.disconnect()

        self.logger.info("✅ Бот остановлен")

    def _validate_config(self):
        """Проверка конфигурации"""
        required_settings = [
            ("MATTERMOST_URL", config.MATTERMOST_URL),
            ("MATTERMOST_TOKEN", config.MATTERMOST_TOKEN),
            ("MATTERMOST_CHANNEL_ID", config.MATTERMOST_CHANNEL_ID),
            ("JIRA_URL", config.JIRA_URL),
        ]

        # Глобальная аутентификация Jira отключена - используются только персональные настройки пользователей

        # Tempo может быть опциональным (если используется только Jira API)
        if config.TEMPO_API_TOKEN:
            required_settings.append(("TEMPO_API_TOKEN", config.TEMPO_API_TOKEN))

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
            me = mattermost_client.driver.users.get_user("me")
            self.logger.info(f"✅ Mattermost: подключен как {me['username']}")
        except Exception as e:
            raise Exception(f"Ошибка подключения к Mattermost: {e}") from e

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
            # Включаем WebSocket для получения сообщений в реальном времени
            self.websocket = True
            self.logger.info("✅ WebSocket включен для получения сообщений")
            self.logger.info("💡 Бот будет отвечать на личные сообщения и команды в каналах")
            self.logger.info("📅 Автоматические проверки выполняются по расписанию")
        except Exception as e:
            self.logger.error(f"❌ Ошибка настройки WebSocket: {e}")
            self.websocket = False

    def _notify_legacy_users(self):
        """Отключить пользователей со старой авторизацией (логин/пароль) и отправить им инструкцию по входу через PAT"""
        legacy_users = db_manager.get_legacy_users_to_notify()
        if not legacy_users:
            return

        self.logger.info(f"🔑 Пользователей со старой авторизацией для уведомления: {len(legacy_users)}")
        message = legacy_user_disabled_message()
        notified_count = 0

        for user_email, user_id in legacy_users:
            sent = False
            try:
                if user_id:
                    sent = mattermost_client.send_direct_message(user_id, message)
                if not sent and not user_email.startswith("user_"):
                    sent = mattermost_client.send_direct_message_by_email(user_email, message)
            except Exception as e:
                self.logger.warning(
                    f"Не удалось отправить уведомление о переходе на PAT пользователю {user_email}: {e}"
                )

            # Пароль удаляем в любом случае; недоставленное уведомление повторим при следующем запуске
            db_manager.disable_legacy_user(user_email, notified=bool(sent))
            if sent:
                notified_count += 1
            else:
                self.logger.warning(f"Уведомление о переходе на PAT не доставлено пользователю {user_email}")

        self.logger.info(f"✅ Уведомления о переходе на PAT отправлены: {notified_count} из {len(legacy_users)}")

    def _send_startup_message(self):
        """Отправить сообщение о запуске бота"""
        try:
            startup_message = f"""🤖 **Бот мониторинга проектов запущен!**

📅 **Расписание:** ежедневно в {config.CHECK_TIME}
🔍 **Активных подписок:** {len(db_manager.get_active_subscriptions())}
⚙️ **Версия:** {datetime.now().strftime("%Y.%m.%d")}

🚨 **Мониторинг:**
• Превышение трудозатрат (факт > план)
• Просроченные сроки выполнения

Используйте `subscribe PROJECT_KEY` для подписки на мониторинг проекта!"""

            mattermost_client.send_channel_message(config.MATTERMOST_CHANNEL_ID, startup_message)

        except Exception as e:
            self.logger.error(f"Ошибка отправки сообщения о запуске: {e}")

    def _send_mode_info(self):
        """Отправить информацию о режиме работы бота"""
        try:
            if self.websocket:
                mode_message = f"""🤖 **Project Monitor Bot запущен**

**Режим работы:**
• ✅ WebSocket активен - бот отвечает на сообщения в реальном времени
• 📅 Автоматические проверки по расписанию в {config.CHECK_TIME}
• 💬 Личные сообщения и команды в каналах работают

**Основные команды:**
• `help` - справка по командам
• `login <PAT>` - войти в Jira по персональному токену (в личных сообщениях)
• `list_projects` - список доступных проектов
• `analytics PROJECT_KEY` / `графики PROJECT_KEY` - аналитика проекта с графиками
• `subscribe PROJECT_KEY` - подписка на мониторинг проекта (в канале)
• `list_subscriptions` - просмотр подписок канала

**⚠️ Важно:** Для работы команд в каналах бот должен быть добавлен в канал!

🔒 **Безопасность:** вход в Jira по Personal Access Token, токены хранятся в зашифрованном виде"""
            else:
                mode_message = f"""🤖 **Project Monitor Bot запущен**

**Режим работы:**
• ⚠️ WebSocket отключен - бот работает только в режиме планировщика
• 📅 Автоматические проверки по расписанию в {config.CHECK_TIME}
• 💬 Личные сообщения и команды недоступны

**Основные функции:**
• Автоматический мониторинг проектов
• Уведомления о превышении трудозатрат
• Уведомления о просроченных сроках

🔒 **Безопасность:** вход в Jira по Personal Access Token, токены хранятся в зашифрованном виде"""

            mattermost_client.send_channel_message(config.MATTERMOST_CHANNEL_ID, mode_message)

        except Exception as e:
            self.logger.error(f"Ошибка отправки информации о режиме: {e}")

    def _run_main_loop(self):
        """Основной цикл работы бота"""
        try:
            if self.websocket:
                # Если WebSocket включен, запускаем прослушивание сообщений
                self.logger.info("🎧 Запуск прослушивания WebSocket сообщений...")
                mattermost_client.start_listening()
            else:
                # Если WebSocket отключен, работаем только в режиме планировщика
                self.logger.info("📅 Работа в режиме планировщика (без WebSocket)")
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


if __name__ == "__main__":
    main()
