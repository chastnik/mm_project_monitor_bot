"""
Планировщик для ежедневных проверок
"""

import logging
import threading
import time
from datetime import datetime
from pathlib import Path

import schedule

from calendar_client import calendar_client
from config import config
from database import db_manager
from mattermost_client import mattermost_client
from project_monitor import project_monitor

logger = logging.getLogger(__name__)


class StandupScheduler:
    def __init__(self):
        self.running = False
        self.scheduler_thread = None
        self._monitoring_lock = threading.Lock()

    def start(self):
        """Запустить планировщик"""
        if self.running:
            logger.warning("Планировщик уже запущен")
            return

        # Настраиваем расписание для мониторинга проектов
        schedule.every().day.at(config.CHECK_TIME).do(self._run_daily_monitoring_in_background)

        # Настраиваем еженедельную проверку календаря (каждый понедельник в 08:00)
        schedule.every().monday.at("08:00").do(self.check_calendar_updates)

        # Загружаем календарь при старте, если еще не загружен
        self._ensure_calendar_loaded()

        self.running = True
        self._touch_heartbeat()
        self.scheduler_thread = threading.Thread(target=self._run_scheduler, daemon=True)
        self.scheduler_thread.start()

        logger.info(f"Планировщик запущен. Ежедневная проверка в {config.CHECK_TIME}")

    def stop(self):
        """Остановить планировщик"""
        self.running = False
        schedule.clear()
        logger.info("Планировщик остановлен")

    def _run_scheduler(self):
        """Основной цикл планировщика"""
        while self.running:
            try:
                schedule.run_pending()
                self._touch_heartbeat()
                time.sleep(60)  # Проверяем каждую минуту
            except Exception as e:
                logger.error(f"Ошибка в планировщике: {e}")
                time.sleep(60)

    @staticmethod
    def _touch_heartbeat():
        """Обновить файл-признак живости (его проверяет HEALTHCHECK контейнера)"""
        try:
            Path(config.HEARTBEAT_FILE).touch()
        except OSError as e:
            logger.debug(f"Не удалось обновить heartbeat: {e}")

    def run_daily_monitoring(self):
        """Выполнить ежедневный мониторинг проектов (выходные и праздники учитывает сам монитор)"""
        logger.info("Запуск ежедневного мониторинга проектов")

        # Если календарь не удалось загрузить ранее, пробуем снова
        self._ensure_calendar_loaded(current_year_only=True)

        try:
            errors = project_monitor.monitor_all_projects()
        except Exception as e:
            logger.error(f"Ошибка при выполнении мониторинга проектов: {e}")
            errors = [f"сбой мониторинга: {e!s}"]

        if errors:
            self._notify_admins_about_errors(errors)
        else:
            logger.info("Ежедневный мониторинг проектов завершен")

    def _notify_admins_about_errors(self, errors: list[str]):
        """Сообщить об ошибках мониторинга в основной канал и администраторам"""
        error_message = "❌ **Ошибки при мониторинге проектов:**\n" + "\n".join(f"• {error}" for error in errors)

        if config.MATTERMOST_CHANNEL_ID:
            mattermost_client.send_channel_message(config.MATTERMOST_CHANNEL_ID, error_message)

        for admin_email in config.ADMIN_EMAILS:
            if admin_email.strip():
                mattermost_client.send_direct_message_by_email(admin_email.strip(), error_message)

    def _run_daily_monitoring_in_background(self):
        """Запуск мониторинга в отдельном потоке: долгая проверка не блокирует цикл планировщика"""
        if not self._monitoring_lock.acquire(blocking=False):
            logger.warning("Предыдущий мониторинг еще выполняется - запуск пропущен")
            return

        def _job():
            try:
                self.run_daily_monitoring()
            finally:
                self._monitoring_lock.release()

        threading.Thread(target=_job, name="daily-monitoring", daemon=True).start()

    def check_calendar_updates(self):
        """Проверить наличие обновлений календаря на текущий и следующий год"""
        logger.info("Запуск еженедельной проверки календаря")

        try:
            current_year = datetime.now().year
            next_year = current_year + 1

            # Проверяем календарь на текущий год
            if not db_manager.is_calendar_loaded(current_year):
                logger.info(f"Загружаем календарь на {current_year} год")
                self._load_calendar_for_year(current_year)
            else:
                logger.info(f"Календарь на {current_year} год уже загружен")
                db_manager.update_calendar_check_date(current_year)

            # Проверяем календарь на следующий год
            if not db_manager.is_calendar_loaded(next_year):
                logger.info(f"Загружаем календарь на {next_year} год")
                self._load_calendar_for_year(next_year)
            else:
                logger.info(f"Календарь на {next_year} год уже загружен")
                db_manager.update_calendar_check_date(next_year)

            logger.info("Еженедельная проверка календаря завершена")

        except Exception as e:
            logger.error(f"Ошибка при проверке календаря: {e}")

    def _ensure_calendar_loaded(self, current_year_only: bool = False):
        """Убедиться, что календарь загружен для текущего (и следующего) года"""
        try:
            current_year = datetime.now().year
            years = [current_year] if current_year_only else [current_year, current_year + 1]

            for year in years:
                if not db_manager.is_calendar_loaded(year):
                    logger.info(f"Загружаем календарь на {year} год при старте")
                    self._load_calendar_for_year(year)
        except Exception as e:
            logger.error(f"Ошибка при загрузке календаря при старте: {e}")

    def _load_calendar_for_year(self, year: int) -> bool:
        """Загрузить производственный календарь на год из API (поденные запросы)"""
        try:
            logger.info(f"Начинаем загрузку производственного календаря на {year} год...")

            # Загружаем все нерабочие дни с описаниями через поденные запросы
            holidays, descriptions = calendar_client.fetch_year_holidays(year)

            if not holidays:
                logger.warning(f"Не найдено нерабочих дней в календаре на {year} год")
                db_manager.update_calendar_check_date(year)
                return False

            # Сохраняем в БД (с описаниями праздников)
            success = db_manager.save_calendar_holidays(year, list(holidays), descriptions)

            if success:
                logger.info(f"Календарь на {year} год успешно загружен ({len(holidays)} нерабочих дней)")
            else:
                logger.error(f"Ошибка сохранения календаря на {year} год")

            return success

        except Exception as e:
            logger.error(f"Ошибка загрузки календаря на {year} год: {e}")
            return False


# Глобальный экземпляр планировщика
scheduler = StandupScheduler()
