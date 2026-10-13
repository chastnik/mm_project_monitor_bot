import os
import sqlite3
import sys
import tempfile
import types
import unittest
from datetime import date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from database import DatabaseManager

_FAKE_MODULES = {
    "mattermost_client": types.SimpleNamespace(
        mattermost_client=types.SimpleNamespace(is_user_admin=lambda email: email == "admin@example.com")
    ),
    "scheduler": types.SimpleNamespace(scheduler=types.SimpleNamespace()),
}


class _DbTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = DatabaseManager(os.path.join(self.tmp.name, "test.db"))

    def tearDown(self):
        self.tmp.cleanup()


class TestCalendarMetadata(_DbTestCase):
    def test_check_date_update_keeps_calendar_loaded(self):
        self.db.save_calendar_holidays(2026, [date(2026, 1, 1)])
        self.assertTrue(self.db.is_calendar_loaded(2026))

        self.db.update_calendar_check_date(2026)

        self.assertTrue(self.db.is_calendar_loaded(2026))
        self.assertEqual(date.today().isoformat(), self.db.get_calendar_check_date(2026))


class TestNotificationHistory(_DbTestCase):
    def save(self, issue_key, channel_id, notification_type="deadline_overdue"):
        self.db.save_notification("PROJ", issue_key, notification_type, None, "Иван", channel_id, "Задача", 0, 0)

    def test_history_is_filtered_by_channel_and_period(self):
        self.save("PROJ-1", "chan1")
        self.save("PROJ-2", "chan2", "time_exceeded")
        with sqlite3.connect(self.db.db_path) as conn:
            conn.execute(
                "UPDATE notification_history SET notification_date = ? WHERE issue_key = 'PROJ-2'",
                ((date.today() - timedelta(days=10)).isoformat(),),
            )

        self.assertEqual(["PROJ-1"], [row[2] for row in self.db.get_notification_history(7, "chan1")])
        self.assertEqual([], self.db.get_notification_history(7, "chan2"))
        self.assertEqual(2, len(self.db.get_notification_history(30)))
        self.assertEqual(date.today().isoformat(), self.db.get_last_notification_date())

    @patch.dict(sys.modules, _FAKE_MODULES)
    def test_history_command_shows_channel_notifications(self):
        import bot_commands

        self.save("PROJ-1", "chan1")
        with patch.object(bot_commands, "db_manager", self.db):
            handler = bot_commands.BotCommandHandler()
            in_channel = handler.handle_message("history", "user@example.com", "O", "chan1", None, "uid1")
            user_dm = handler.handle_message("history", "user@example.com", "D", "dm1", None, "uid1")
            admin_dm = handler.handle_message("history 3", "admin@example.com", "D", "dm2", None, "uid2")

        self.assertIn("PROJ-1", in_channel)
        self.assertIn("просрочен срок", in_channel)
        self.assertNotIn("PROJ-1", user_dm)
        self.assertIn("во всех каналах", admin_dm)
        self.assertIn("PROJ-1", admin_dm)


def _issue_with_status_changes(status, changes):
    histories = [
        SimpleNamespace(
            created=f"{changed_on.isoformat()}T10:00:00.000+0300",
            items=[SimpleNamespace(field="status", toString=to_status)],
        )
        for changed_on, to_status in changes
    ]
    return SimpleNamespace(
        key="PROJ-1",
        fields=SimpleNamespace(status=SimpleNamespace(name=status)),
        changelog=SimpleNamespace(histories=histories),
    )


@patch.dict(sys.modules, _FAKE_MODULES)
class TestIssueClosedRecently(unittest.TestCase):
    def test_uses_latest_close_after_reopen(self):
        from project_monitor import ProjectMonitor

        today = date.today()
        issue = _issue_with_status_changes(
            "Done",
            [(today - timedelta(days=30), "Done"), (today - timedelta(days=20), "In Progress"), (today, "Done")],
        )
        self.assertTrue(ProjectMonitor().is_issue_closed_recently(issue))

    def test_old_close_is_not_recent(self):
        from project_monitor import ProjectMonitor

        issue = _issue_with_status_changes("Done", [(date.today() - timedelta(days=30), "Done")])
        self.assertFalse(ProjectMonitor().is_issue_closed_recently(issue))


class TestCalendarTimeout(unittest.TestCase):
    def test_requests_use_timeout(self):
        from calendar_client import REQUEST_TIMEOUT, CalendarClient

        client = CalendarClient("https://calendar.example.com")
        client.session = MagicMock()
        client.get_day_info(2026, 1, 1)

        _, kwargs = client.session.get.call_args
        self.assertEqual(REQUEST_TIMEOUT, kwargs["timeout"])


class TestAnalyticsMonths(unittest.TestCase):
    @patch.dict(sys.modules, {"user_jira_client": types.SimpleNamespace(user_jira_client=MagicMock())})
    def test_chart_includes_current_month(self):
        import project_analytics

        created = datetime.now().strftime("%Y-%m-%dT10:00:00.000+0300")
        issue = SimpleNamespace(
            fields=SimpleNamespace(
                status=SimpleNamespace(name="Open"),
                assignee=None,
                issuetype=SimpleNamespace(name="Task"),
                timeoriginalestimate=0,
                timespent=0,
                duedate=None,
                created=created,
            )
        )
        fake_client = MagicMock()
        fake_client.get_project_issues.return_value = ([issue], 1)

        captured = {}
        real_subplots = project_analytics.plt.subplots

        def spy_subplots(*args, **kwargs):
            fig, axes = real_subplots(*args, **kwargs)
            captured["axes"] = axes
            return fig, axes

        with (
            tempfile.TemporaryDirectory() as out_dir,
            patch.object(project_analytics.config, "ARTIFACTS_DIR", out_dir, create=True),
            patch.object(project_analytics.plt, "subplots", side_effect=spy_subplots),
            # Модуль мог быть импортирован другим тестом раньше - подменяем клиент Jira напрямую
            patch.object(project_analytics, "user_jira_client", fake_client),
        ):
            _, image_path = project_analytics.ProjectAnalytics().build_project_analytics("u@example.com", "PROJ")
            self.assertTrue(os.path.exists(image_path))

        month_labels = [label.get_text() for label in captured["axes"][1].get_xticklabels()]
        self.assertEqual(6, len(month_labels))
        self.assertEqual(datetime.now().strftime("%Y-%m"), month_labels[-1])


class TestAdminCheck(unittest.TestCase):
    def test_admin_check_is_case_insensitive_and_rejects_empty(self):
        # Модуль подключается к Mattermost при импорте, поэтому подменяем драйвер
        with patch.dict(sys.modules, {"mattermostdriver": types.SimpleNamespace(Driver=MagicMock())}):
            sys.modules.pop("mattermost_client", None)
            import mattermost_client

        with patch.object(mattermost_client.config, "ADMIN_EMAILS", ["Admin@Example.com", ""]):
            client = mattermost_client.MattermostClient.__new__(mattermost_client.MattermostClient)
            self.assertTrue(client.is_user_admin("admin@example.com"))
            self.assertFalse(client.is_user_admin(""))
            self.assertFalse(client.is_user_admin("user@example.com"))


if __name__ == "__main__":
    unittest.main()
