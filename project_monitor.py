"""
Модуль мониторинга проектов - проверка превышения трудозатрат и просроченных сроков
"""
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional
from database import db_manager
from mattermost_client import mattermost_client
from user_jira_client import user_jira_client
from config import config

logger = logging.getLogger(__name__)

class ProjectMonitor:
    def __init__(self):
        self.closed_statuses = ['Done', 'Closed', 'Resolved', 'Выполнено', 'Закрыто', 'Готово', 'Отменено', 'Отказ', 'Отклонено', 'Отклонен', 'Отклонена', 'Отклонены', 'Отложено', 'Не прошел испытательный срок', 'Выполнено частично', 'Отменён', 'Прошел испытательный срок', 'Отказ от оффера ']
        
    def monitor_all_projects(self):
        """Мониторинг всех активных проектов"""
        logger.info("Начинаем мониторинг всех активных проектов")
        
        try:
            # Получаем все активные подписки
            subscriptions = db_manager.get_active_subscriptions()
            
            if not subscriptions:
                logger.info("Нет активных подписок на проекты")
                return
            
            logger.info(f"Найдено {len(subscriptions)} активных подписок")
            
            for project_key, project_name, channel_id, team_id, subscribed_by in subscriptions:
                try:
                    logger.info(f"Мониторинг проекта {project_key}")
                    self.monitor_project(project_key, project_name, channel_id)
                except Exception as e:
                    logger.error(f"Ошибка мониторинга проекта {project_key}: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"Ошибка мониторинга проектов: {e}")
    
    def monitor_project(self, project_key: str, project_name: str, channel_id: str):
        """Мониторинг конкретного проекта"""
        logger.info(f"Проверяем проект {project_key}")
        
        try:
            # Получаем подписку для определения пользователя, создавшего её
            subscriptions = db_manager.get_subscriptions_by_channel(channel_id)
            project_subscription = None
            
            for subscription in subscriptions:
                if subscription[0] == project_key:  # project_key
                    project_subscription = subscription
                    break
            
            if not project_subscription:
                logger.error(f"Подписка на проект {project_key} не найдена в канале {channel_id}")
                return
            
            # Извлекаем email пользователя, создавшего подписку
            subscribed_by_email = project_subscription[2]  # subscribed_by_email
            
            # Получаем все задачи проекта через персональное подключение
            issues = self.get_project_issues(subscribed_by_email, project_key)
            
            if not issues:
                logger.warning(f"Нет задач в проекте {project_key} или нет доступа")
                return
            
            logger.info(f"Найдено {len(issues)} задач в проекте {project_key}")
            
            notifications_sent = 0
            
            for issue in issues:
                try:
                    # Проверяем превышение трудозатрат
                    if self.check_time_exceeded(issue):
                        self.send_time_exceeded_notification(issue, project_key, channel_id)
                        notifications_sent += 1
                    
                    # Проверяем просроченные сроки
                    if self.check_deadline_overdue(issue):
                        self.send_deadline_notification(issue, project_key, channel_id)
                        notifications_sent += 1
                        
                    # Обновляем кеш задачи
                    self.update_issue_in_cache(issue, project_key)
                    
                except Exception as e:
                    logger.error(f"Ошибка проверки задачи {issue.key}: {e}")
                    continue
            
            logger.info(f"Проект {project_key}: отправлено {notifications_sent} уведомлений")
            
        except Exception as e:
            logger.error(f"Ошибка мониторинга проекта {project_key}: {e}")
    
    def monitor_project_for_channel(self, project_key: str, channel_id: str) -> str:
        """Мониторинг конкретного проекта для канала с возвратом результата"""
        logger.info(f"Ручная проверка проекта {project_key} для канала {channel_id}")
        
        try:
            # Получаем подписку для определения пользователя, создавшего её
            subscriptions = db_manager.get_subscriptions_by_channel(channel_id)
            project_subscription = None
            
            for subscription in subscriptions:
                if subscription[0] == project_key:  # project_key в позиции 0
                    project_subscription = subscription
                    break
            
            if not project_subscription:
                return f"Подписка на проект не найдена в канале"
            
            # Извлекаем данные подписки
            # subscription: (project_key, project_name, subscribed_by_email, created_at, active)
            project_name = project_subscription[1]  # project_name
            subscribed_by_email = project_subscription[2]  # subscribed_by_email
            
            # Получаем все задачи проекта через персональное подключение
            issues = self.get_project_issues(subscribed_by_email, project_key)
            
            if not issues:
                return f"Нет задач в проекте или нет доступа"
            
            logger.info(f"Найдено {len(issues)} задач в проекте {project_key}")
            
            problems_found = []
            
            for issue in issues:
                try:
                    # Проверяем превышение трудозатрат
                    if self.check_time_exceeded(issue):
                        problems_found.append(f"⏱️ {issue.key}: превышение трудозатрат")
                    
                    # Проверяем просроченные сроки
                    if self.check_deadline_overdue(issue):
                        problems_found.append(f"📅 {issue.key}: просроченный срок")
                        
                except Exception as e:
                    logger.error(f"Ошибка проверки задачи {issue.key}: {e}")
                    problems_found.append(f"❌ {issue.key}: ошибка проверки")
                    continue
            
            if problems_found:
                result = f"найдено проблем: {len(problems_found)}"
                # Отправляем уведомления для найденных проблем
                for issue in issues:
                    try:
                        if self.check_time_exceeded(issue):
                            self.send_time_exceeded_notification(issue, project_key, channel_id)
                        if self.check_deadline_overdue(issue):
                            self.send_deadline_notification(issue, project_key, channel_id)
                    except Exception as e:
                        logger.error(f"Ошибка отправки уведомления для {issue.key}: {e}")
            else:
                result = "проблем не найдено"
            
            logger.info(f"Проект {project_key}: {result}")
            return result
            
        except Exception as e:
            logger.error(f"Ошибка мониторинга проекта {project_key}: {e}")
            return f"ошибка проверки: {str(e)}"
    
    def get_project_issues(self, user_email: str, project_key: str) -> List:
        """Получить все задачи проекта через персональное подключение"""
        try:
            # Используем персональное подключение пользователя
            issues = user_jira_client.get_project_issues(user_email, project_key)
            
            if issues is None:
                logger.error(f"Не удалось получить задачи проекта {project_key} для пользователя {user_email}")
                return []
            
            logger.debug(f"Получено {len(issues)} задач для проекта {project_key}")
            return issues
            
        except Exception as e:
            logger.error(f"Ошибка получения задач проекта {project_key}: {e}")
            return []
    
    def check_time_exceeded(self, issue) -> bool:
        """Проверить превышение трудозатрат"""
        try:
            # Получаем временные данные
            original_estimate = getattr(issue.fields, 'timeoriginalestimate', 0) or 0
            time_spent = getattr(issue.fields, 'timespent', 0) or 0
            
            if original_estimate == 0:
                return False  # Нет плановой оценки - не проверяем
            
            # Проверяем превышение (факт > план)
            if time_spent > original_estimate:
                # Дополнительная проверка для закрытых задач
                if self.is_issue_closed_recently(issue):
                    return True
                elif not self.is_issue_closed(issue):
                    return True
            
            return False
            
        except Exception as e:
            logger.error(f"Ошибка проверки трудозатрат для {issue.key}: {e}")
            return False
    
    def check_deadline_overdue(self, issue) -> bool:
        """Проверить просроченные сроки"""
        try:
            # Проверяем срок выполнения
            due_date = getattr(issue.fields, 'duedate', None)
            
            if not due_date:
                return False  # Нет срока - не проверяем
            
            # Парсим дату
            due_datetime = datetime.strptime(due_date, '%Y-%m-%d')
            today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            
            # Проверяем: срок <= сегодня И задача не закрыта
            if due_datetime <= today and not self.is_issue_closed(issue):
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Ошибка проверки сроков для {issue.key}: {e}")
            return False
    
    def is_issue_closed(self, issue) -> bool:
        """Проверить, закрыта ли задача"""
        try:
            status_name = issue.fields.status.name
            return status_name in self.closed_statuses
        except:
            return False
    
    def is_issue_closed_recently(self, issue) -> bool:
        """Проверить, была ли задача закрыта недавно (не позднее вчера)"""
        try:
            if not self.is_issue_closed(issue):
                return False
            
            # Ищем в истории изменений когда задача была закрыта
            if hasattr(issue, 'changelog') and issue.changelog:
                for history in issue.changelog.histories:
                    for item in history.items:
                        if item.field == 'status' and item.toString in self.closed_statuses:
                            # Парсим дату изменения статуса
                            changed_date = datetime.strptime(history.created[:10], '%Y-%m-%d')
                            yesterday = datetime.now() - timedelta(days=1)
                            yesterday = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
                            
                            # Задача закрыта не раньше вчера
                            return changed_date >= yesterday
            
            return False
            
        except Exception as e:
            logger.error(f"Ошибка проверки даты закрытия для {issue.key}: {e}")
            return False
    
    def send_time_exceeded_notification(self, issue, project_key: str, channel_id: str):
        """Отправить уведомление о превышении трудозатрат"""
        try:
            # Получаем данные о времени
            original_estimate = (getattr(issue.fields, 'timeoriginalestimate', 0) or 0) / 3600.0
            time_spent = (getattr(issue.fields, 'timespent', 0) or 0) / 3600.0
            
            # Получаем информацию об ответственном
            assignee_email, assignee_name = self.get_assignee_info(issue)
            
            # Формируем сообщения
            channel_message = self.format_time_exceeded_message(
                issue.key, issue.fields.summary, assignee_name, 
                original_estimate, time_spent, True  # для канала
            )
            
            personal_message = self.format_time_exceeded_message(
                issue.key, issue.fields.summary, assignee_name,
                original_estimate, time_spent, False  # для личного сообщения
            )
            
            # Отправляем уведомления
            mattermost_client.send_channel_message(channel_id, channel_message)
            
            if assignee_email:
                mattermost_client.send_direct_message_by_email(assignee_email, personal_message)
            
            # Сохраняем в историю
            db_manager.save_notification(
                project_key, issue.key, 'time_exceeded',
                assignee_email, assignee_name, channel_id,
                issue.fields.summary, original_estimate, time_spent
            )
            
            logger.info(f"Отправлено уведомление о превышении времени: {issue.key}")
            
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления о времени для {issue.key}: {e}")
    
    def send_deadline_notification(self, issue, project_key: str, channel_id: str):
        """Отправить уведомление о просроченном сроке"""
        try:
            # Получаем информацию об ответственном
            assignee_email, assignee_name = self.get_assignee_info(issue)
            
            due_date = getattr(issue.fields, 'duedate', None)
            
            # Формируем сообщения
            channel_message = self.format_deadline_message(
                issue.key, issue.fields.summary, assignee_name, due_date, True
            )
            
            personal_message = self.format_deadline_message(
                issue.key, issue.fields.summary, assignee_name, due_date, False
            )
            
            # Отправляем уведомления
            mattermost_client.send_channel_message(channel_id, channel_message)
            
            if assignee_email:
                mattermost_client.send_direct_message_by_email(assignee_email, personal_message)
            
            # Сохраняем в историю
            db_manager.save_notification(
                project_key, issue.key, 'deadline_overdue',
                assignee_email, assignee_name, channel_id,
                issue.fields.summary, 0, 0, due_date
            )
            
            logger.info(f"Отправлено уведомление о просрочке: {issue.key}")
            
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления о сроке для {issue.key}: {e}")
    
    def get_assignee_info(self, issue) -> Tuple[Optional[str], str]:
        """Получить информацию об ответственном за задачу"""
        try:
            if issue.fields.assignee:
                assignee_name = issue.fields.assignee.displayName
                assignee_email = getattr(issue.fields.assignee, 'emailAddress', None)
                return assignee_email, assignee_name
            else:
                return None, "Не назначен"
        except:
            return None, "Не назначен"
    
    def update_issue_in_cache(self, issue, project_key: str):
        """Обновить информацию о задаче в кеше"""
        try:
            assignee_email, assignee_name = self.get_assignee_info(issue)
            
            original_estimate = (getattr(issue.fields, 'timeoriginalestimate', 0) or 0) / 3600.0
            time_spent = (getattr(issue.fields, 'timespent', 0) or 0) / 3600.0
            remaining_estimate = (getattr(issue.fields, 'timeestimate', 0) or 0) / 3600.0
            
            due_date = getattr(issue.fields, 'duedate', None)
            status = issue.fields.status.name
            
            db_manager.update_issue_cache(
                issue.key, project_key, issue.fields.summary,
                assignee_email, assignee_name, status, due_date,
                original_estimate, time_spent, remaining_estimate
            )
            
        except Exception as e:
            logger.error(f"Ошибка обновления кеша для {issue.key}: {e}")
    
    def format_time_exceeded_message(self, issue_key: str, summary: str, assignee: str,
                                   planned_hours: float, actual_hours: float, for_channel: bool) -> str:
        """Форматировать сообщение о превышении времени"""
        excess_hours = actual_hours - planned_hours
        
        # Создаем ссылку на задачу в Jira
        jira_url = f"{config.JIRA_URL}/browse/{issue_key}"
        task_link = f"[{issue_key}]({jira_url})"
        
        if for_channel:
            return f"""🚨 **Превышение трудозатрат**

📋 **Задача:** {task_link} - {summary[:50]}{'...' if len(summary) > 50 else ''}
👤 **Ответственный:** {assignee}
⏱️ **Плановые часы:** {planned_hours:.1f}ч
📈 **Фактические часы:** {actual_hours:.1f}ч
❗ **Превышение:** {excess_hours:.1f}ч

Требует внимания руководителя проекта!"""
        else:
            return f"""🚨 **Превышение трудозатрат по вашей задаче**

📋 **Задача:** {task_link} - {summary}
⏱️ **Плановые часы:** {planned_hours:.1f}ч  
📈 **Фактические часы:** {actual_hours:.1f}ч
❗ **Превышение:** {excess_hours:.1f}ч

Пожалуйста, свяжитесь с руководителем проекта для обсуждения ситуации."""
    
    def format_deadline_message(self, issue_key: str, summary: str, assignee: str,
                               due_date: str, for_channel: bool) -> str:
        """Форматировать сообщение о просроченном сроке"""
        try:
            due_datetime = datetime.strptime(due_date, '%Y-%m-%d')
            formatted_date = due_datetime.strftime('%d.%m.%Y')
        except:
            formatted_date = due_date
        
        # Создаем ссылку на задачу в Jira
        jira_url = f"{config.JIRA_URL}/browse/{issue_key}"
        task_link = f"[{issue_key}]({jira_url})"
        
        if for_channel:
            return f"""⏰ **Просрочен срок выполнения**

📋 **Задача:** {task_link} - {summary[:50]}{'...' if len(summary) > 50 else ''}
👤 **Ответственный:** {assignee}
📅 **Срок выполнения:** {formatted_date}
❗ **Статус:** Просрочено

Задача требует немедленного внимания!"""
        else:
            return f"""⏰ **Просрочен срок по вашей задаче**

📋 **Задача:** {task_link} - {summary}
📅 **Срок выполнения был:** {formatted_date}

Пожалуйста, обновите статус задачи или свяжитесь с руководителем проекта."""

# Глобальный экземпляр монитора
project_monitor = ProjectMonitor()
