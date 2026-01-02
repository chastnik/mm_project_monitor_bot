"""
Планировщик для ежедневных проверок
"""
import schedule
import time
import logging
import threading
from datetime import datetime, date
from typing import List, Tuple
from config import config
from database import db_manager
from mattermost_client import mattermost_client
from project_monitor import project_monitor
from calendar_client import calendar_client

logger = logging.getLogger(__name__)

class StandupScheduler:
    def __init__(self):
        self.running = False
        self.scheduler_thread = None
    
    def start(self):
        """Запустить планировщик"""
        if self.running:
            logger.warning("Планировщик уже запущен")
            return
        
        # Настраиваем расписание для мониторинга проектов
        schedule.every().day.at(config.CHECK_TIME).do(self.run_daily_monitoring)
        
        # Настраиваем еженедельную проверку календаря (каждый понедельник в 08:00)
        schedule.every().monday.at("08:00").do(self.check_calendar_updates)
        
        # Загружаем календарь при старте, если еще не загружен
        self._ensure_calendar_loaded()
        
        self.running = True
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
                time.sleep(60)  # Проверяем каждую минуту
            except Exception as e:
                logger.error(f"Ошибка в планировщике: {e}")
                time.sleep(60)
    
    def run_daily_monitoring(self):
        """Выполнить ежедневный мониторинг проектов"""
        logger.info("Запуск ежедневного мониторинга проектов")
        
        try:
            # Проверяем, не является ли сегодня выходным или праздничным днем
            today = date.today()
            if db_manager.is_holiday(today):
                logger.info(f"Сегодня ({today}) выходной или праздничный день - мониторинг пропущен")
                return
            
            # Дополнительная проверка через API (на случай, если календарь не загружен)
            if not calendar_client.is_working_day(today):
                logger.info(f"Сегодня ({today}) выходной или праздничный день (проверено через API) - мониторинг пропущен")
                return
            
            # Запускаем мониторинг всех активных проектов
            project_monitor.monitor_all_projects()
            
            logger.info("Ежедневный мониторинг проектов завершен")
            
        except Exception as e:
            logger.error(f"Ошибка при выполнении мониторинга проектов: {e}")
            
            # Отправляем уведомление об ошибке администраторам
            error_message = f"❌ Ошибка при мониторинге проектов: {str(e)}"
            
            # Отправляем в основной канал если он настроен
            if config.MATTERMOST_CHANNEL_ID:
                mattermost_client.send_channel_message(config.MATTERMOST_CHANNEL_ID, error_message)
            
            # Отправляем администраторам
            for admin_email in config.ADMIN_EMAILS:
                if admin_email.strip():
                    mattermost_client.send_direct_message_by_email(admin_email.strip(), error_message)
    
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
    
    def _ensure_calendar_loaded(self):
        """Убедиться, что календарь загружен для текущего и следующего года"""
        try:
            current_year = datetime.now().year
            next_year = current_year + 1
            
            for year in [current_year, next_year]:
                if not db_manager.is_calendar_loaded(year):
                    logger.info(f"Загружаем календарь на {year} год при старте")
                    self._load_calendar_for_year(year)
        except Exception as e:
            logger.error(f"Ошибка при загрузке календаря при старте: {e}")
    
    def _load_calendar_for_year(self, year: int) -> bool:
        """Загрузить календарь на год из API"""
        try:
            calendar_data = calendar_client.get_year_calendar(year)
            if not calendar_data:
                logger.error(f"Не удалось получить календарь на {year} год")
                return False
            
            # Извлекаем выходные и праздничные дни
            holidays = calendar_client.extract_holidays_from_calendar(calendar_data, year)
            
            if not holidays:
                logger.warning(f"Не найдено выходных дней в календаре на {year} год")
                # Помечаем календарь как загруженный, даже если не нашли праздники
                # (возможно, структура ответа другая)
                db_manager.update_calendar_check_date(year)
                return False
            
            # Сохраняем в БД
            success = db_manager.save_calendar_holidays(year, list(holidays))
            
            if success:
                logger.info(f"Календарь на {year} год успешно загружен ({len(holidays)} выходных дней)")
            else:
                logger.error(f"Ошибка сохранения календаря на {year} год")
            
            return success
            
        except Exception as e:
            logger.error(f"Ошибка загрузки календаря на {year} год: {e}")
            return False
    
    def _send_channel_report(self, users_with_data: List[str], users_without_data: List[str], report_type: str = "worklog"):
        """Отправить отчет в канал"""
        try:
            # Получаем только имена для канального сообщения (без email)
            users_with_names = [name.split(' (')[0] for name in users_with_data]
            users_without_names = [name.split(' (')[0] for name in users_without_data]
            
            if report_type == "plans":
                message = mattermost_client.format_plans_report_message(users_with_names, users_without_names)
            else:
                message = mattermost_client.format_user_list_message(users_with_names, users_without_names)
            
            success = mattermost_client.send_channel_message(config.MATTERMOST_CHANNEL_ID, message)
            if success:
                logger.info("Отчет отправлен в канал")
            else:
                logger.error("Ошибка отправки отчета в канал")
                
        except Exception as e:
            logger.error(f"Ошибка формирования отчета для канала: {e}")
    
    def _send_personal_reminders(self, users_without_data: List[str], results: dict, reminder_type: str = "worklog"):
        """Отправить персональные напоминания"""
        for user_info in users_without_data:
            try:
                # Извлекаем email из строки "Name (email)"
                email = user_info.split('(')[1].split(')')[0]
                display_name = user_info.split(' (')[0]
                
                # Формируем персональное сообщение в зависимости от типа
                if reminder_type == "plans":
                    message = mattermost_client.format_plans_reminder_message(display_name)
                else:
                    message = mattermost_client.format_reminder_message(display_name)
                
                # Отправляем личное сообщение
                success = mattermost_client.send_direct_message_by_email(email, message)
                if success:
                    reminder_word = "напоминание о планах" if reminder_type == "plans" else "напоминание"
                    logger.info(f"{reminder_word} отправлено пользователю {display_name} ({email})")
                else:
                    logger.warning(f"Не удалось отправить напоминание пользователю {email}")
                    
            except Exception as e:
                logger.error(f"Ошибка отправки напоминания пользователю {user_info}: {e}")
    
    def run_manual_check(self) -> str:
        """Запустить проверку вручную (для команд администратора)"""
        try:
            logger.info("Запуск ручной проверки заполнения планов")
            
            # Выполняем проверку
            self.run_daily_check()
            
            return "✅ Ручная проверка выполнена успешно"
            
        except Exception as e:
            error_msg = f"❌ Ошибка при ручной проверке: {str(e)}"
            logger.error(error_msg)
            return error_msg

# Глобальный экземпляр планировщика
scheduler = StandupScheduler()
