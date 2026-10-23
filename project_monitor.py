"""
Модуль мониторинга проектов - проверка превышения трудозатрат и просроченных сроков
"""

import logging
from collections import defaultdict
from datetime import date, datetime, timedelta

from calendar_client import calendar_client
from config import config
from database import db_manager
from jira_constants import CLOSED_STATUSES
from mattermost_client import mattermost_client
from user_jira_client import user_jira_client

logger = logging.getLogger(__name__)

TIME_EXCEEDED = "time_exceeded"
DEADLINE_OVERDUE = "deadline_overdue"

# Сколько задач помещается в одно сообщение-дайджест (лимит длины поста в Mattermost)
DIGEST_CHUNK_SIZE = 15
SUMMARY_MAX_LENGTH = 80


class ProjectMonitor:
    def __init__(self):
        self.closed_statuses = CLOSED_STATUSES

    def _is_working_day_today(self) -> bool:
        """Рабочий ли сегодня день (выходные, производственный календарь в БД, затем API)"""
        today = date.today()

        if today.weekday() >= 5:
            logger.info(f"Сегодня ({today}) выходной день (суббота/воскресенье) - мониторинг пропущен")
            return False

        if db_manager.is_holiday(today):
            logger.info(f"Сегодня ({today}) праздничный день - мониторинг пропущен")
            return False

        # Дополнительная проверка через API (на случай, если календарь не загружен)
        if not calendar_client.is_working_day(today):
            logger.info(f"Сегодня ({today}) нерабочий день (проверено через API) - мониторинг пропущен")
            return False

        return True

    def monitor_all_projects(self, force: bool = False) -> list[str]:
        """Мониторинг всех активных подписок. force=True игнорирует выходные и праздники.

        Возвращает список описаний ошибок (пустой, если все прошло успешно или мониторинг пропущен).
        """
        logger.info("Начинаем мониторинг всех активных проектов")

        if not force and not self._is_working_day_today():
            return []

        subscriptions = db_manager.get_active_subscriptions()
        if not subscriptions:
            logger.info("Нет активных подписок на проекты")
            return []

        logger.info(f"Найдено {len(subscriptions)} активных подписок")

        errors: list[str] = []
        for project_key, project_name, channel_id, _team_id, _subscribed_by in subscriptions:
            try:
                logger.info(f"Мониторинг проекта {project_key}")
                error = self.monitor_project(project_key, project_name, channel_id)
            except Exception as e:
                logger.error(f"Ошибка мониторинга проекта {project_key}: {e}")
                error = f"неожиданная ошибка: {e}"
            if error:
                errors.append(f"{project_key} (канал {channel_id}): {error}")

        return errors

    def _find_subscription(self, project_key: str, channel_id: str):
        for subscription in db_manager.get_subscriptions_by_channel(channel_id):
            if subscription[0] == project_key:
                return subscription
        return None

    def monitor_project(self, project_key: str, project_name: str, channel_id: str) -> str | None:
        """Мониторинг конкретного проекта. Возвращает описание ошибки или None, если проверка прошла."""
        logger.info(f"Проверяем проект {project_key}")

        subscription = self._find_subscription(project_key, channel_id)
        if not subscription:
            logger.error(f"Подписка на проект {project_key} не найдена в канале {channel_id}")
            return "подписка не найдена"

        # subscription: (project_key, project_name, subscribed_by_email, created_at, active)
        subscribed_by_email = subscription[2]

        issues = self.get_project_issues(subscribed_by_email, project_key)
        if issues is None:
            return (
                f"не удалось получить задачи от имени {subscribed_by_email} "
                f"(токен недействителен, нет доступа или Jira недоступна)"
            )

        logger.info(f"Найдено {len(issues)} задач в проекте {project_key}")

        problems = self.collect_problems(issues, update_cache_project=project_key)
        sent = self.notify_problems(problems, project_key, channel_id)
        logger.info(f"Проект {project_key}: найдено проблем {len(problems)}, отправлено уведомлений {sent}")
        return None

    def monitor_project_for_channel(self, project_key: str, channel_id: str) -> str:
        """Мониторинг конкретного проекта для канала с возвратом результата"""
        logger.info(f"Ручная проверка проекта {project_key} для канала {channel_id}")

        try:
            subscription = self._find_subscription(project_key, channel_id)
            if not subscription:
                return "Подписка на проект не найдена в канале"

            subscribed_by_email = subscription[2]

            if not db_manager.get_user_jira_settings(subscribed_by_email):
                return (
                    f"автор подписки ({subscribed_by_email}) не вошел в Jira по токену — "
                    f"ему нужно выполнить `login <PAT>` в личных сообщениях боту, "
                    f"либо переподпишите канал от своего имени: `subscribe {project_key}`"
                )

            issues = self.get_project_issues(subscribed_by_email, project_key)
            if issues is None:
                return "не удалось получить задачи проекта (токен недействителен, нет доступа или Jira недоступна)"

            problems = self.collect_problems(issues)
            if not problems:
                return "проблем не найдено"

            sent = self.notify_problems(problems, project_key, channel_id)
            result = f"найдено проблем: {len(problems)}"
            if sent < len(problems):
                result += f" (новых уведомлений: {sent}, остальные уже отправлялись сегодня)"
            logger.info(f"Проект {project_key}: {result}")
            return result

        except Exception as e:
            logger.error(f"Ошибка мониторинга проекта {project_key}: {e}")
            return f"ошибка проверки: {e!s}"

    def get_project_issues(self, user_email: str, project_key: str) -> list | None:
        """Получить задачи проекта через персональное подключение. None - ошибка получения."""
        try:
            issues = user_jira_client.get_issues_for_monitoring(user_email, project_key)
            if issues is None:
                logger.error(f"Не удалось получить задачи проекта {project_key} для пользователя {user_email}")
                return None

            logger.debug(f"Получено {len(issues)} задач для проекта {project_key}")
            return issues

        except Exception as e:
            logger.error(f"Ошибка получения задач проекта {project_key}: {e}")
            return None

    def collect_problems(self, issues: list, update_cache_project: str | None = None) -> list[tuple]:
        """Найти проблемные задачи: список (задача, тип проблемы)"""
        problems: list[tuple] = []
        for issue in issues:
            try:
                if self.check_time_exceeded(issue):
                    problems.append((issue, TIME_EXCEEDED))
                if self.check_deadline_overdue(issue):
                    problems.append((issue, DEADLINE_OVERDUE))
                if update_cache_project:
                    self.update_issue_in_cache(issue, update_cache_project)
            except Exception as e:
                logger.error(f"Ошибка проверки задачи {issue.key}: {e}")
        return problems

    def check_time_exceeded(self, issue) -> bool:
        """Проверить превышение трудозатрат"""
        try:
            # Получаем временные данные
            original_estimate = getattr(issue.fields, "timeoriginalestimate", 0) or 0
            time_spent = getattr(issue.fields, "timespent", 0) or 0

            if original_estimate == 0:
                return False  # Нет плановой оценки - не проверяем

            # Проверяем превышение (факт > план)
            return time_spent > original_estimate and (
                self.is_issue_closed_recently(issue) or not self.is_issue_closed(issue)
            )

        except Exception as e:
            logger.error(f"Ошибка проверки трудозатрат для {issue.key}: {e}")
            return False

    def check_deadline_overdue(self, issue) -> bool:
        """Проверить просроченные сроки"""
        try:
            # Проверяем срок выполнения
            due_date = getattr(issue.fields, "duedate", None)

            if not due_date:
                return False  # Нет срока - не проверяем

            # Парсим дату
            due_datetime = datetime.strptime(due_date, "%Y-%m-%d")
            today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

            # Проверяем: срок <= сегодня И задача не закрыта
            return due_datetime <= today and not self.is_issue_closed(issue)

        except Exception as e:
            logger.error(f"Ошибка проверки сроков для {issue.key}: {e}")
            return False

    def is_issue_closed(self, issue) -> bool:
        """Проверить, закрыта ли задача"""
        try:
            status_name = issue.fields.status.name
            return status_name in self.closed_statuses
        except Exception:
            return False

    def is_issue_closed_recently(self, issue) -> bool:
        """Проверить, была ли задача закрыта недавно (не позднее вчера)"""
        try:
            if not self.is_issue_closed(issue):
                return False

            if not (hasattr(issue, "changelog") and issue.changelog):
                return False

            # Ищем в истории изменений последнее закрытие (задачу могли переоткрыть и закрыть снова)
            close_dates = [
                datetime.strptime(history.created[:10], "%Y-%m-%d")
                for history in issue.changelog.histories
                for item in history.items
                if item.field == "status" and item.toString in self.closed_statuses
            ]
            if not close_dates:
                return False

            yesterday = (datetime.now() - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)

            # Задача закрыта не раньше вчера
            return max(close_dates) >= yesterday

        except Exception as e:
            logger.error(f"Ошибка проверки даты закрытия для {issue.key}: {e}")
            return False

    def notify_problems(self, problems: list[tuple], project_key: str, channel_id: str) -> int:
        """Отправить уведомления дайджестами: по несколько задач в одном посте канала и по одному ЛС на исполнителя.

        Уведомления, уже отправленные в этот канал сегодня, пропускаются. Возвращает число новых уведомлений.
        """
        new_problems = [
            (issue, kind) for issue, kind in problems if not db_manager.was_notified_today(issue.key, kind, channel_id)
        ]
        if not new_problems:
            return 0

        for kind in (TIME_EXCEEDED, DEADLINE_OVERDUE):
            items = [issue for issue, problem_kind in new_problems if problem_kind == kind]
            for start in range(0, len(items), DIGEST_CHUNK_SIZE):
                chunk = items[start : start + DIGEST_CHUNK_SIZE]
                if not mattermost_client.send_channel_message(
                    channel_id, self.format_channel_digest(project_key, kind, chunk)
                ):
                    logger.error(f"Не удалось отправить дайджест по проекту {project_key} в канал {channel_id}")
                    # Не записываем в историю неотправленное: повторим при следующей проверке
                    new_problems = [(i, k) for i, k in new_problems if k != kind or i not in chunk]

        # Личные сообщения: одно на исполнителя со всеми его задачами
        by_assignee: dict[str, list[tuple]] = defaultdict(list)
        for issue, kind in new_problems:
            assignee_email, _ = self.get_assignee_info(issue)
            if assignee_email:
                by_assignee[assignee_email].append((issue, kind))
        for assignee_email, assignee_problems in by_assignee.items():
            mattermost_client.send_direct_message_by_email(
                assignee_email, self.format_personal_digest(assignee_problems)
            )

        for issue, kind in new_problems:
            self.save_problem_notification(issue, kind, project_key, channel_id)

        return len(new_problems)

    def save_problem_notification(self, issue, kind: str, project_key: str, channel_id: str):
        """Сохранить отправленное уведомление в историю"""
        assignee_email, assignee_name = self.get_assignee_info(issue)
        if kind == TIME_EXCEEDED:
            planned, actual = self._hours(issue)
            due_date = None
        else:
            planned, actual = 0, 0
            due_date = getattr(issue.fields, "duedate", None)
        db_manager.save_notification(
            project_key,
            issue.key,
            kind,
            assignee_email,
            assignee_name,
            channel_id,
            issue.fields.summary,
            planned,
            actual,
            due_date,
        )

    @staticmethod
    def _hours(issue) -> tuple[float, float]:
        planned = (getattr(issue.fields, "timeoriginalestimate", 0) or 0) / 3600.0
        actual = (getattr(issue.fields, "timespent", 0) or 0) / 3600.0
        return planned, actual

    def get_assignee_info(self, issue) -> tuple[str | None, str]:
        """Получить информацию об ответственном за задачу"""
        try:
            if issue.fields.assignee:
                assignee_name = issue.fields.assignee.displayName
                assignee_email = getattr(issue.fields.assignee, "emailAddress", None)
                return assignee_email, assignee_name
            else:
                return None, "Не назначен"
        except Exception:
            return None, "Не назначен"

    def update_issue_in_cache(self, issue, project_key: str):
        """Обновить информацию о задаче в кеше"""
        try:
            assignee_email, assignee_name = self.get_assignee_info(issue)

            original_estimate = (getattr(issue.fields, "timeoriginalestimate", 0) or 0) / 3600.0
            time_spent = (getattr(issue.fields, "timespent", 0) or 0) / 3600.0
            remaining_estimate = (getattr(issue.fields, "timeestimate", 0) or 0) / 3600.0

            due_date = getattr(issue.fields, "duedate", None)
            status = issue.fields.status.name

            db_manager.update_issue_cache(
                issue.key,
                project_key,
                issue.fields.summary,
                assignee_email,
                assignee_name,
                status,
                due_date,
                original_estimate,
                time_spent,
                remaining_estimate,
            )

        except Exception as e:
            logger.error(f"Ошибка обновления кеша для {issue.key}: {e}")

    def _issue_link(self, issue_key: str) -> str:
        return f"[{issue_key}]({config.JIRA_URL}/browse/{issue_key})"

    @staticmethod
    def _short(summary: str) -> str:
        summary = summary or ""
        return summary[:SUMMARY_MAX_LENGTH] + ("..." if len(summary) > SUMMARY_MAX_LENGTH else "")

    @staticmethod
    def _format_due_date(due_date: str | None) -> str:
        try:
            return datetime.strptime(due_date, "%Y-%m-%d").strftime("%d.%m.%Y")
        except Exception:
            return str(due_date)

    def _problem_line(self, issue, kind: str, with_assignee: bool) -> str:
        line = f"• {self._issue_link(issue.key)} - {self._short(issue.fields.summary)}"
        details = []
        if with_assignee:
            details.append(f"👤 {self.get_assignee_info(issue)[1]}")
        if kind == TIME_EXCEEDED:
            planned, actual = self._hours(issue)
            details.append(f"план {planned:.1f}ч, факт {actual:.1f}ч, превышение {actual - planned:.1f}ч")
        else:
            details.append(f"срок {self._format_due_date(getattr(issue.fields, 'duedate', None))}")
        return f"{line}\n  {'; '.join(details)}"

    def format_channel_digest(self, project_key: str, kind: str, issues: list) -> str:
        """Сообщение в канал: несколько задач одного типа проблемы"""
        if kind == TIME_EXCEEDED:
            title = f"🚨 **Превышение трудозатрат - {project_key} ({len(issues)})**"
            footer = "Требует внимания руководителя проекта!"
        else:
            title = f"⏰ **Просрочен срок выполнения - {project_key} ({len(issues)})**"
            footer = "Задачи требуют немедленного внимания!"
        lines = [self._problem_line(issue, kind, with_assignee=True) for issue in issues]
        return f"{title}\n\n" + "\n".join(lines) + f"\n\n{footer}"

    def format_personal_digest(self, problems: list[tuple]) -> str:
        """Личное сообщение исполнителю со всеми его проблемными задачами"""
        lines = []
        exceeded = [issue for issue, kind in problems if kind == TIME_EXCEEDED]
        overdue = [issue for issue, kind in problems if kind == DEADLINE_OVERDUE]
        if exceeded:
            lines.append("🚨 **Превышение трудозатрат по вашим задачам:**")
            lines.extend(self._problem_line(issue, TIME_EXCEEDED, with_assignee=False) for issue in exceeded)
            lines.append("")
        if overdue:
            lines.append("⏰ **Просрочен срок по вашим задачам:**")
            lines.extend(self._problem_line(issue, DEADLINE_OVERDUE, with_assignee=False) for issue in overdue)
            lines.append("")
        lines.append("Пожалуйста, обновите статус задач или свяжитесь с руководителем проекта.")
        return "\n".join(lines)


# Глобальный экземпляр монитора
project_monitor = ProjectMonitor()
