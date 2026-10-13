import os
import sqlite3
import sys
import tempfile
import types
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

# matplotlib (и numpy) импортируем заранее: patch.dict(sys.modules) выгружает модули, загруженные внутри него,
# а numpy нельзя загрузить в процесс повторно
import matplotlib.pyplot  # noqa: F401

from database import DatabaseManager

TOKEN = "test-token-" + "y" * 30


class TestKeyReset(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = DatabaseManager(os.path.join(self.tmp.name, "test.db"))

    def tearDown(self):
        self.tmp.cleanup()

    def test_tokens_are_reset_on_first_run_and_on_key_change(self):
        self.db.save_user_jira_settings("ivan@example.com", "uid1", "ivan", TOKEN)

        # Первый запуск после обновления: отпечатка еще нет, токены от старого ключа сбрасываются
        self.assertEqual(1, self.db.reset_tokens_if_key_changed("fingerprint-a"))
        self.assertIsNone(self.db.get_user_jira_settings("ivan@example.com"))
        self.assertEqual([("ivan@example.com", "uid1", "pat_reset")], self.db.get_legacy_users_to_notify())

        # Тот же ключ - ничего не сбрасывается
        self.db.disable_legacy_user("ivan@example.com", notified=True)
        self.db.save_user_jira_settings("ivan@example.com", "uid1", "ivan", TOKEN)
        self.assertEqual(0, self.db.reset_tokens_if_key_changed("fingerprint-a"))
        self.assertEqual(TOKEN, self.db.get_user_jira_settings("ivan@example.com")[2])

        # Ключ сменили - токен снова сброшен и пользователь снова получит уведомление
        self.assertEqual(1, self.db.reset_tokens_if_key_changed("fingerprint-b"))
        self.assertEqual([("ivan@example.com", "uid1", "pat_reset")], self.db.get_legacy_users_to_notify())
        with sqlite3.connect(self.db.db_path) as conn:
            self.assertEqual("", conn.execute("SELECT jira_password FROM user_jira_settings").fetchone()[0])

    def test_password_users_keep_legacy_status(self):
        with sqlite3.connect(self.db.db_path) as conn:
            conn.execute(
                "INSERT INTO user_jira_settings (user_email, user_id, jira_username, jira_password) VALUES (?, ?, ?, ?)",
                ("old@example.com", "uid2", "old", "secret"),
            )
        self.db.reset_tokens_if_key_changed("fingerprint-a")
        self.assertEqual([("old@example.com", "uid2", "password")], self.db.get_legacy_users_to_notify())


class TestStartupNotifications(unittest.TestCase):
    def test_message_depends_on_reason(self):
        mm = MagicMock()
        mm.send_direct_message.return_value = True
        fake_db = MagicMock()
        fake_db.get_legacy_users_to_notify.return_value = [
            ("old@example.com", "uid1", "password"),
            ("ivan@example.com", "uid2", "pat_reset"),
        ]
        with patch.dict(
            sys.modules,
            {
                "mattermost_client": types.SimpleNamespace(mattermost_client=mm),
                "scheduler": types.SimpleNamespace(scheduler=MagicMock()),
            },
        ):
            sys.modules.pop("main", None)
            import main

            with patch.object(main, "db_manager", fake_db), patch.object(main, "mattermost_client", mm):
                main.StandupBot()._notify_legacy_users()

        messages = {call.args[0]: call.args[1] for call in mm.send_direct_message.call_args_list}
        self.assertIn("логину и паролю отключен", messages["uid1"])
        self.assertIn("Нужно заново войти", messages["uid2"])
        self.assertEqual(2, fake_db.disable_legacy_user.call_count)


class _Page(list):
    def __init__(self, items, total):
        super().__init__(items)
        self.total = total


@patch.dict(
    sys.modules,
    {
        # Настоящий модуль подключается к Mattermost при импорте
        "mattermost_client": types.SimpleNamespace(mattermost_client=MagicMock()),
    },
)
class TestAnalyticsPagination(unittest.TestCase):
    def make_client(self, total, server_page_limit=1000):
        import user_jira_client

        jira = MagicMock()

        def search(jql, startAt=0, maxResults=50, expand=None):
            size = min(maxResults, server_page_limit, max(total - startAt, 0))
            return _Page([f"ISSUE-{startAt + i}" for i in range(size)], total)

        jira.search_issues.side_effect = search
        client = user_jira_client.UserJiraClient()
        client.get_jira_client = lambda _email: jira
        return client, jira

    def test_fetches_up_to_limit_across_pages(self):
        client, jira = self.make_client(total=12000)
        issues, total = client.get_project_issues("u@example.com", "PROJ", max_results=5000)

        self.assertEqual(5000, len(issues))
        self.assertEqual(12000, total)
        self.assertEqual(5, jira.search_issues.call_count)
        self.assertEqual(len(set(issues)), len(issues))

    def test_server_with_smaller_page_limit(self):
        client, jira = self.make_client(total=1500, server_page_limit=100)
        issues, total = client.get_project_issues("u@example.com", "PROJ", max_results=5000)

        self.assertEqual(1500, len(issues))
        self.assertEqual(1500, total)
        self.assertEqual(15, jira.search_issues.call_count)

    def test_report_warns_when_project_is_larger_than_limit(self):
        import project_analytics

        issue = SimpleNamespace(
            fields=SimpleNamespace(
                status=SimpleNamespace(name="Open"),
                assignee=None,
                issuetype=SimpleNamespace(name="Task"),
                timeoriginalestimate=0,
                timespent=0,
                duedate=None,
                created=None,
            )
        )
        fake_client = MagicMock()
        fake_client.get_project_issues.return_value = ([issue], 7000)
        with (
            tempfile.TemporaryDirectory() as out_dir,
            patch.object(project_analytics, "user_jira_client", fake_client),
            patch.object(project_analytics.config, "ARTIFACTS_DIR", out_dir, create=True),
        ):
            report, _ = project_analytics.ProjectAnalytics().build_project_analytics("u@example.com", "PROJ")

        self.assertEqual(5000, fake_client.get_project_issues.call_args.kwargs["max_results"])
        self.assertIn("Учтены 1 последних обновленных задач из 7000", report)


if __name__ == "__main__":
    unittest.main()
