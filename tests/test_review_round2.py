import os
import sqlite3
import sys
import tempfile
import types
import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


def _issue(key, summary="Задача", spent=7200, estimate=3600, due=None, assignee_email="dev@example.com"):
    return SimpleNamespace(
        key=key,
        fields=SimpleNamespace(
            summary=summary,
            timeoriginalestimate=estimate,
            timespent=spent,
            duedate=due,
            status=SimpleNamespace(name="Open"),
            assignee=SimpleNamespace(displayName="Иван", emailAddress=assignee_email),
        ),
    )


class TestEnvBool(unittest.TestCase):
    def test_unknown_value_keeps_verification_enabled(self):
        import config

        with patch.dict(os.environ, {"X_FLAG": "maybe"}):
            self.assertTrue(config._env_bool("X_FLAG"))

    def test_common_values(self):
        import config

        for raw, expected in [("1", True), ("Yes", True), ("false", False), ("0", False), ("OFF", False)]:
            with patch.dict(os.environ, {"X_FLAG": raw}):
                self.assertEqual(expected, config._env_bool("X_FLAG"), raw)


class TestCommandAliases(unittest.TestCase):
    def test_resolves_multiword_and_args(self):
        from command_aliases import resolve_command

        self.assertEqual(("subscribe", ["IDB"]), resolve_command(["подпиши", "на", "проект", "IDB"]))
        self.assertEqual(("setup_jira", ["tok"]), resolve_command(["login", "tok"]))
        self.assertEqual((None, ["привет"]), resolve_command(["привет"]))

    def test_substring_is_not_a_command(self):
        from command_aliases import resolve_command

        self.assertEqual(None, resolve_command(["вот", "такой", "проект"])[0])


class TestAuthErrors(unittest.TestCase):
    def setUp(self):
        patcher = patch.dict(sys.modules, {"mattermost_client": types.SimpleNamespace(mattermost_client=MagicMock())})
        patcher.start()
        self.addCleanup(patcher.stop)
        sys.modules.pop("user_jira_client", None)
        self.addCleanup(sys.modules.pop, "user_jira_client", None)

    def test_only_401_is_auth_error(self):
        from jira.exceptions import JIRAError

        from user_jira_client import _is_auth_error

        self.assertTrue(_is_auth_error(JIRAError(status_code=401)))
        self.assertFalse(_is_auth_error(JIRAError(status_code=403, text="CAPTCHA_CHALLENGE")))
        self.assertFalse(_is_auth_error(JIRAError(status_code=500, text="credentials")))

    def test_cache_is_lru_and_clear_keeps_limit(self):
        from user_jira_client import UserJiraClient

        client = UserJiraClient(max_cache_size=2)
        client._add_to_cache("a", 1)
        client._add_to_cache("b", 2)
        client.clear_user_cache("a")
        client._add_to_cache("c", 3)
        client._add_to_cache("d", 4)
        self.assertEqual(["c", "d"], list(client.jira_instances))


class TestCalendarIncomplete(unittest.TestCase):
    def test_failed_days_raise_instead_of_marking_year_loaded(self):
        from calendar_client import CalendarClient, CalendarLoadError

        client = CalendarClient("http://x")
        client.get_day_info = lambda y, m, d: None
        with self.assertRaises(CalendarLoadError):
            client.fetch_year_holidays(2026)


class TestDatabase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "t.db")

    def tearDown(self):
        self.tmp.cleanup()

    def test_notification_unique_per_channel_and_migration(self):
        # Старая схема: уникальность без канала
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                """CREATE TABLE notification_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, project_key TEXT NOT NULL, issue_key TEXT NOT NULL,
                    notification_type TEXT NOT NULL, assignee_email TEXT, assignee_name TEXT,
                    channel_id TEXT NOT NULL, issue_summary TEXT, planned_hours REAL DEFAULT 0,
                    actual_hours REAL DEFAULT 0, due_date DATE, notification_date DATE NOT NULL,
                    sent_to_channel BOOLEAN DEFAULT 0, sent_to_assignee BOOLEAN DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(issue_key, notification_type, notification_date))"""
            )
            conn.execute(
                "INSERT INTO notification_history (project_key, issue_key, notification_type, channel_id, notification_date)"
                " VALUES ('P','P-1','time_exceeded','c1','2026-01-01')"
            )

        from database import DatabaseManager

        db = DatabaseManager(self.path)
        self.assertEqual(1, len(db.get_notification_history(days=3650)))

        db.save_notification("P", "P-2", "time_exceeded", None, "И", "c1", "s", 1, 2)
        db.save_notification("P", "P-2", "time_exceeded", None, "И", "c2", "s", 1, 2)
        self.assertTrue(db.was_notified_today("P-2", "time_exceeded", "c1"))
        self.assertTrue(db.was_notified_today("P-2", "time_exceeded", "c2"))
        self.assertFalse(db.was_notified_today("P-2", "time_exceeded", "c3"))
        self.assertEqual(date.today().isoformat(), db.get_last_notification_date())

    def test_email_lookup_is_case_insensitive(self):
        from database import DatabaseManager

        db = DatabaseManager(self.path)
        self.assertTrue(db.save_user_jira_settings("User@Example.com", "uid", "jira.user", "tok"))
        self.assertIsNotNone(db.get_user_jira_settings("USER@example.com"))


class TestMonitorDigest(unittest.TestCase):
    def setUp(self):
        self.mm = MagicMock()
        self.mm.send_channel_message.return_value = True
        self.db = MagicMock()
        self.db.was_notified_today.return_value = False
        modules = {
            "mattermost_client": types.SimpleNamespace(mattermost_client=self.mm),
            "user_jira_client": types.SimpleNamespace(user_jira_client=MagicMock()),
        }
        self.patcher = patch.dict(sys.modules, modules)
        self.patcher.start()
        sys.modules.pop("project_monitor", None)
        import project_monitor

        self.pm = project_monitor.ProjectMonitor()
        self.module = project_monitor
        self.module.db_manager = self.db

    def tearDown(self):
        sys.modules.pop("project_monitor", None)
        self.patcher.stop()

    def test_one_channel_post_and_one_dm_per_assignee(self):
        problems = [(_issue(f"P-{i}"), "time_exceeded") for i in range(3)]
        sent = self.pm.notify_problems(problems, "P", "chan")
        self.assertEqual(3, sent)
        self.assertEqual(1, self.mm.send_channel_message.call_count)
        self.assertEqual(1, self.mm.send_direct_message_by_email.call_count)
        self.assertEqual(3, self.db.save_notification.call_count)

    def test_long_list_is_chunked(self):
        problems = [(_issue(f"P-{i}"), "time_exceeded") for i in range(35)]
        self.pm.notify_problems(problems, "P", "chan")
        self.assertEqual(3, self.mm.send_channel_message.call_count)

    def test_already_notified_today_is_skipped(self):
        self.db.was_notified_today.return_value = True
        sent = self.pm.notify_problems([(_issue("P-1"), "time_exceeded")], "P", "chan")
        self.assertEqual(0, sent)
        self.mm.send_channel_message.assert_not_called()

    def test_failed_channel_post_is_not_recorded(self):
        self.mm.send_channel_message.return_value = False
        sent = self.pm.notify_problems([(_issue("P-1"), "time_exceeded")], "P", "chan")
        self.assertEqual(0, sent)
        self.db.save_notification.assert_not_called()

    def test_fetch_failure_is_reported_as_error(self):
        self.db.get_active_subscriptions.return_value = [("P", "Proj", "chan", None, "a@example.com")]
        self.db.get_subscriptions_by_channel.return_value = [("P", "Proj", "a@example.com", "2026-01-01", 1)]
        self.pm.get_project_issues = lambda *_: None
        errors = self.pm.monitor_all_projects(force=True)
        self.assertEqual(1, len(errors))
        self.assertIn("P", errors[0])


class TestMentions(unittest.TestCase):
    def _client(self):
        with patch.dict(sys.modules, {"mattermostdriver": types.SimpleNamespace(Driver=MagicMock())}):
            sys.modules.pop("mattermost_client", None)
            import mattermost_client
        self.addCleanup(sys.modules.pop, "mattermost_client", None)
        client = mattermost_client.MattermostClient.__new__(mattermost_client.MattermostClient)
        client.bot_username = "projbot"
        return client

    def test_mention_matches_whole_name_only(self):
        client = self._client()
        self.assertTrue(client._is_bot_mentioned("@projbot help"))
        self.assertTrue(client._is_bot_mentioned("привет @Jora, help"))
        self.assertFalse(client._is_bot_mentioned("@projbot2 help"))
        self.assertFalse(client._is_bot_mentioned("@asking help"))

    def test_remove_mention_and_command_detection(self):
        client = self._client()
        self.assertEqual("графики IDB", client._remove_bot_mention("@projbot графики IDB"))
        self.assertEqual("analytics", client._get_main_command("графики IDB"))
        self.assertEqual("unknown", client._get_main_command("расскажи про проект"))
        self.assertEqual("monitor_now", client._get_main_command("monitor_now"))


if __name__ == "__main__":
    unittest.main()
