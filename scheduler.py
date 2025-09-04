"""
Планировщик для ежедневных проверок
"""
import schedule
import time
import logging
import threading
from datetime import datetime
from typing import List, Tuple
from config import config
from database import db_manager
from mattermost_client import mattermost_client
from jira_tempo_client import jira_tempo_client

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
        
        # Настраиваем расписание
        schedule.every().day.at(config.CHECK_TIME).do(self.run_daily_check)
        
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
    
    def run_daily_check(self):
        """Выполнить ежедневную проверку"""
        logger.info("Запуск ежедневной проверки заполнения планов")
        
        try:
            # Получаем список активных пользователей
            users = db_manager.get_active_users()
            if not users:
                logger.warning("Нет активных пользователей для проверки")
                return
            
            # Извлекаем email адреса
            user_emails = [user[0] for user in users]  # email - первый элемент
            logger.info(f"Проверяем {len(user_emails)} пользователей")
            
            # Определяем дату для проверки (вчерашний день для утренней проверки)
            check_date = jira_tempo_client.get_yesterday_date()
            
            # Проверяем worklog в Jira/Tempo
            worklog_results = jira_tempo_client.check_users_worklog_for_date(user_emails, check_date)
            
            # Разделяем пользователей на группы
            users_with_worklog = []
            users_without_worklog = []
            
            for email, (has_worklog, hours, display_name) in worklog_results.items():
                # Сохраняем результат в БД
                db_manager.save_check_result(email, check_date, has_worklog, hours)
                
                if has_worklog:
                    users_with_worklog.append(f"{display_name} ({email}) - {hours:.1f}ч")
                else:
                    users_without_worklog.append(f"{display_name} ({email})")
            
            # Отправляем отчет в канал
            self._send_channel_report(users_with_worklog, users_without_worklog)
            
            # Отправляем персональные напоминания
            self._send_personal_reminders(users_without_worklog, worklog_results)
            
            logger.info(f"Ежедневная проверка завершена. "
                       f"С worklog: {len(users_with_worklog)}, "
                       f"Без worklog: {len(users_without_worklog)}")
            
        except Exception as e:
            logger.error(f"Ошибка при выполнении ежедневной проверки: {e}")
            # Отправляем сообщение об ошибке в канал
            error_message = f"❌ Ошибка при выполнении проверки планов: {str(e)}"
            mattermost_client.send_channel_message(config.MATTERMOST_CHANNEL_ID, error_message)
    
    def _send_channel_report(self, users_with_worklog: List[str], users_without_worklog: List[str]):
        """Отправить отчет в канал"""
        try:
            # Получаем только имена для канального сообщения (без email)
            users_with_names = [name.split(' (')[0] for name in users_with_worklog]
            users_without_names = [name.split(' (')[0] for name in users_without_worklog]
            
            message = mattermost_client.format_user_list_message(users_with_names, users_without_names)
            
            success = mattermost_client.send_channel_message(config.MATTERMOST_CHANNEL_ID, message)
            if success:
                logger.info("Отчет отправлен в канал")
            else:
                logger.error("Ошибка отправки отчета в канал")
                
        except Exception as e:
            logger.error(f"Ошибка формирования отчета для канала: {e}")
    
    def _send_personal_reminders(self, users_without_worklog: List[str], worklog_results: dict):
        """Отправить персональные напоминания"""
        for user_info in users_without_worklog:
            try:
                # Извлекаем email из строки "Name (email)"
                email = user_info.split('(')[1].split(')')[0]
                display_name = user_info.split(' (')[0]
                
                # Формируем персональное сообщение
                message = mattermost_client.format_reminder_message(display_name)
                
                # Отправляем личное сообщение
                success = mattermost_client.send_direct_message_by_email(email, message)
                if success:
                    logger.info(f"Напоминание отправлено пользователю {display_name} ({email})")
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
