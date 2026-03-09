"""
Аналитика проекта из Jira: сбор метрик и построение графиков
"""

import logging
import os
from datetime import datetime, timedelta

import matplotlib

matplotlib.use("Agg")  # Рендер без X-сервера
import matplotlib.pyplot as plt

from config import config
from user_jira_client import user_jira_client

logger = logging.getLogger(__name__)


class ProjectAnalytics:
    def __init__(self):
        pass

    def build_project_analytics(self, user_email: str, project_key: str) -> tuple[str, str | None]:
        """Собрать текстовый отчет и сгенерировать .jpg с графиками"""
        issues = user_jira_client.get_project_issues(user_email, project_key, max_results=1000)
        if not issues:
            return f"ℹ️ Нет данных по проекту {project_key} или нет доступа", None

        # Метрики
        total = len(issues)
        closed_statuses = [
            "Done",
            "Closed",
            "Resolved",
            "Выполнено",
            "Закрыто",
            "Готово",
            "Отменено",
            "Отклонено",
            "Отложено",
        ]
        closed = 0
        overdue_count = 0
        over_estimate_count = 0
        over_by_user: dict[str, int] = {}
        overdue_by_user: dict[str, int] = {}

        # Метрики только по открытым задачам (актуальные)
        open_over_estimate_count = 0
        open_overdue_count = 0
        open_over_by_user: dict[str, int] = {}
        open_overdue_by_user: dict[str, int] = {}

        points_x: list[float] = []  # оценка (часы)
        points_y: list[float] = []  # факт (часы)

        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

        created_per_month: dict[str, int] = {}
        closed_per_month: dict[str, int] = {}
        six_months_ago = (today.replace(day=1) - timedelta(days=180)).replace(day=1)

        assignee_total: dict[str, int] = {}
        assignee_open: dict[str, int] = {}
        type_counts: dict[str, int] = {}

        for issue in issues:
            fields = issue.fields

            status_name = getattr(fields.status, "name", "") if getattr(fields, "status", None) else ""
            is_closed = status_name in closed_statuses
            if is_closed:
                closed += 1
            # Исполнители: считаем всего и активные
            assignee_name = None
            if getattr(fields, "assignee", None):
                assignee_name = getattr(fields.assignee, "displayName", None) or "Не назначен"
            else:
                assignee_name = "Не назначен"
            assignee_total[assignee_name] = assignee_total.get(assignee_name, 0) + 1
            if not is_closed:
                assignee_open[assignee_name] = assignee_open.get(assignee_name, 0) + 1

            # Тип задачи
            issue_type = getattr(getattr(fields, "issuetype", None), "name", "Unknown") or "Unknown"
            type_counts[issue_type] = type_counts.get(issue_type, 0) + 1

            # Оценка и факт (секунды -> часы)
            orig = (getattr(fields, "timeoriginalestimate", 0) or 0) / 3600.0
            spent = (getattr(fields, "timespent", 0) or 0) / 3600.0
            if orig > 0 and spent >= 0:
                points_x.append(orig)
                points_y.append(spent)
                if spent > orig:
                    over_estimate_count += 1
                    assignee_name = None
                    if getattr(fields, "assignee", None):
                        assignee_name = getattr(fields.assignee, "displayName", None) or "Не назначен"
                    over_by_user[assignee_name or "Не назначен"] = (
                        over_by_user.get(assignee_name or "Не назначен", 0) + 1
                    )
                    if not is_closed:
                        open_over_estimate_count += 1
                        open_over_by_user[assignee_name or "Не назначен"] = (
                            open_over_by_user.get(assignee_name or "Не назначен", 0) + 1
                        )

            # Просрочки
            due_date = getattr(fields, "duedate", None)
            if due_date and not is_closed:
                try:
                    due_dt = datetime.strptime(due_date, "%Y-%m-%d")
                    if due_dt <= today:
                        overdue_count += 1
                        assignee_name = None
                        if getattr(fields, "assignee", None):
                            assignee_name = getattr(fields.assignee, "displayName", None) or "Не назначен"
                        overdue_by_user[assignee_name or "Не назначен"] = (
                            overdue_by_user.get(assignee_name or "Не назначен", 0) + 1
                        )
                        open_overdue_count += 1
                        open_overdue_by_user[assignee_name or "Не назначен"] = (
                            open_overdue_by_user.get(assignee_name or "Не назначен", 0) + 1
                        )
                except Exception:
                    pass

            # Created/Closed per month (последние 6 мес)
            try:
                created_raw = getattr(fields, "created", None)
                if created_raw:
                    created_dt = datetime.strptime(created_raw[:10], "%Y-%m-%d")
                    if created_dt >= six_months_ago:
                        key = created_dt.strftime("%Y-%m")
                        created_per_month[key] = created_per_month.get(key, 0) + 1
            except Exception:
                pass

            # Определяем дату закрытия из changelog
            try:
                if hasattr(issue, "changelog") and issue.changelog:
                    for history in issue.changelog.histories:
                        for item in history.items:
                            if item.field == "status" and item.toString in closed_statuses:
                                closed_dt = datetime.strptime(history.created[:10], "%Y-%m-%d")
                                if closed_dt >= six_months_ago:
                                    key = closed_dt.strftime("%Y-%m")
                                    closed_per_month[key] = closed_per_month.get(key, 0) + 1
                                # берем только первое закрытие
                                raise StopIteration
            except StopIteration:
                pass
            except Exception:
                pass

        open_ = total - closed

        def dict_max_key(d: dict[str, int]) -> tuple[str, int] | None:
            if not d:
                return None
            k = max(d, key=lambda x: d[x])
            return k, d[k]

        over_top = dict_max_key(over_by_user)
        overdue_top = dict_max_key(overdue_by_user)
        open_over_top = dict_max_key(open_over_by_user)
        open_overdue_top = dict_max_key(open_overdue_by_user)

        # Формируем текстовый отчет
        lines = [
            f"📊 **Аналитика проекта `{project_key}`**",
            f"• Всего задач: {total}",
            f"• Открытых: {open_}",
            f"• Закрытых: {closed}",
            f"• С превышением трудозатрат: {over_estimate_count}",
            f"• Просроченных: {overdue_count}",
        ]
        if over_top:
            lines.append(f"• Больше всего превышений: {over_top[0]} ({over_top[1]})")
        if overdue_top:
            lines.append(f"• Больше всего просрочек: {overdue_top[0]} ({overdue_top[1]})")

        # Блок по открытым задачам (актуальные)
        lines.append("")
        lines.append("📌 **Актуально (по открытым задачам):**")
        lines.append(f"• Превышений: {open_over_estimate_count}")
        lines.append(f"• Просроченных: {open_overdue_count}")
        if open_over_top:
            lines.append(f"• Больше всего превышений: {open_over_top[0]} ({open_over_top[1]})")
        if open_overdue_top:
            lines.append(f"• Больше всего просрочек: {open_overdue_top[0]} ({open_overdue_top[1]})")

        # Блок по исполнителям
        lines.append("")
        lines.append("👥 **Исполнители (всего / активные):**")
        # Сортировка по общему числу задач по убыванию
        for name in sorted(assignee_total.keys(), key=lambda k: assignee_total[k], reverse=True):
            total_cnt = assignee_total.get(name, 0)
            open_cnt = assignee_open.get(name, 0)
            lines.append(f"• {name}: {total_cnt} / {open_cnt}")

        report_text = "\n".join(lines)

        # Рисуем графики: scatter и created vs closed за 6 мес
        image_path = None
        try:
            fig, axes = plt.subplots(1, 3, figsize=(16, 5))

            # Scatter: оценка vs факт
            axes[0].scatter(points_x, points_y, alpha=0.6, s=20)
            max_axis = max(points_x + points_y) if (points_x and points_y) else 1
            axes[0].plot([0, max_axis], [0, max_axis], "r--", linewidth=1)
            axes[0].set_title("Оценка vs Факт (часы)")
            axes[0].set_xlabel("Оценка")
            axes[0].set_ylabel("Факт")

            # Created/Closed per month (упорядочим последние 6 месяцев)
            months = []
            cursor = six_months_ago
            for _ in range(6):
                months.append(cursor.strftime("%Y-%m"))
                # следующий месяц
                next_month = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)
                cursor = next_month

            created_vals = [created_per_month.get(m, 0) for m in months]
            closed_vals = [closed_per_month.get(m, 0) for m in months]

            x = list(range(len(months)))
            axes[1].plot(x, created_vals, label="Создано", marker="o")
            axes[1].plot(x, closed_vals, label="Закрыто", marker="o")
            axes[1].set_title("Создано vs Закрыто (6 мес)")
            axes[1].set_xticks(x)
            axes[1].set_xticklabels(months, rotation=45, ha="right")
            axes[1].legend()

            # Pie: распределение по типам задач
            if type_counts:
                labels = list(type_counts.keys())
                sizes = list(type_counts.values())
                axes[2].pie(sizes, labels=labels, autopct="%1.0f%%", startangle=140)
                axes[2].axis("equal")
                axes[2].set_title("Типы задач")
            else:
                axes[2].text(0.5, 0.5, "Нет данных по типам", ha="center", va="center")
                axes[2].set_axis_off()

            plt.tight_layout()

            out_dir = getattr(config, "ARTIFACTS_DIR", "/tmp")
            os.makedirs(out_dir, exist_ok=True)
            image_path = os.path.join(out_dir, f"{project_key}_analytics_{int(datetime.now().timestamp())}.jpg")
            fig.savefig(image_path, format="jpg", dpi=150)
            plt.close(fig)
        except Exception as e:
            logger.error(f"Ошибка построения графиков: {e}")

        return report_text, image_path
