import os
import sqlite3
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

from auth_messages import mask_secrets
from database import DatabaseManager

_FAKE_MODULES = {
    "mattermost_client": types.SimpleNamespace(
        mattermost_client=types.SimpleNamespace(is_user_admin=lambda _email: False)
    ),
    "scheduler": types.SimpleNamespace(scheduler=types.SimpleNamespace()),
}

TOKEN = "test-token-" + "x" * 30


class _FakeUserJiraClient:
    def __init__(self, username=None, error=None):
        self.username = username
        self.error = error
        self.verified_tokens = []

    def verify_token(self, token):
        self.verified_tokens.append(token)
        return self.username, self.error

    def clear_user_cache(self, _email):
        pass

    def test_connection(self, _email):
        return True, "✅ Подключение успешно!"


class _DbTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = DatabaseManager(os.path.join(self.tmp.name, "test.db"))

    def tearDown(self):
        self.tmp.cleanup()

    def insert_legacy_user(self, email, user_id="uid1"):
        with sqlite3.connect(self.db.db_path) as conn:
            conn.execute(
                "INSERT INTO user_jira_settings (user_email, user_id, jira_username, jira_password) VALUES (?, ?, ?, ?)",
                (email, user_id, "olduser", "encrypted-old-password"),
            )


class TestLegacyMigration(_DbTestCase):
    def test_legacy_user_is_not_returned_as_configured(self):
        self.insert_legacy_user("old@example.com")
        self.assertIsNone(self.db.get_user_jira_settings("old@example.com"))
        self.assertEqual([("old@example.com", "uid1")], self.db.get_legacy_users_to_notify())

    def test_disable_legacy_user_wipes_password_and_marks_notified(self):
        self.insert_legacy_user("old@example.com")
        self.assertTrue(self.db.disable_legacy_user("old@example.com", notified=True))

        with sqlite3.connect(self.db.db_path) as conn:
            password, notified_at = conn.execute(
                "SELECT jira_password, pat_migration_notified_at FROM user_jira_settings"
            ).fetchone()
        self.assertEqual("", password)
        self.assertIsNotNone(notified_at)
        self.assertEqual([], self.db.get_legacy_users_to_notify())

    def test_undelivered_notification_is_retried(self):
        self.insert_legacy_user("old@example.com")
        self.db.disable_legacy_user("old@example.com", notified=False)
        self.assertEqual([("old@example.com", "uid1")], self.db.get_legacy_users_to_notify())

    def test_login_with_pat_replaces_legacy_settings(self):
        self.insert_legacy_user("old@example.com")
        self.db.disable_legacy_user("old@example.com", notified=True)

        self.assertTrue(self.db.save_user_jira_settings("old@example.com", "uid1", "ivan", TOKEN))

        settings = self.db.get_user_jira_settings("old@example.com")
        self.assertEqual(("uid1", "ivan", TOKEN, 1), settings)
        self.assertEqual([], self.db.get_legacy_users_to_notify())
        self.assertEqual([("old@example.com", "ivan", "pat")], self.db.get_all_jira_users())


@patch.dict(sys.modules, _FAKE_MODULES)
class TestLoginCommand(_DbTestCase):
    def run_command(self, text, fake_jira, channel_type="D"):
        import bot_commands

        with (
            patch.object(bot_commands, "db_manager", self.db),
            patch.dict(sys.modules, {"user_jira_client": types.SimpleNamespace(user_jira_client=fake_jira)}),
        ):
            return bot_commands.BotCommandHandler().handle_message(
                text, "ivan@example.com", channel_type, "chan1", None, "uid1"
            )

    def test_login_saves_verified_token(self):
        fake_jira = _FakeUserJiraClient(username="ivan")
        result = self.run_command(f"login {TOKEN}", fake_jira)

        self.assertIn("Вход в Jira выполнен", result)
        self.assertEqual([TOKEN], fake_jira.verified_tokens)
        self.assertEqual(TOKEN, self.db.get_user_jira_settings("ivan@example.com")[2])

    def test_invalid_token_is_not_saved(self):
        fake_jira = _FakeUserJiraClient(error="Токен недействителен, истек или был отозван")
        result = self.run_command(f"войти {TOKEN}", fake_jira)

        self.assertIn("Не удалось войти", result)
        self.assertIsNone(self.db.get_user_jira_settings("ivan@example.com"))

    def test_login_and_password_is_rejected(self):
        fake_jira = _FakeUserJiraClient(username="ivan")
        result = self.run_command("setup_jira ivan secret", fake_jira)

        self.assertIn("логину и паролю больше не поддерживается", result)
        self.assertEqual([], fake_jira.verified_tokens)

    def test_token_in_channel_is_rejected(self):
        fake_jira = _FakeUserJiraClient(username="ivan")
        result = self.run_command(f"login {TOKEN}", fake_jira, channel_type="O")

        self.assertIn("отзовите этот токен", result)
        self.assertEqual([], fake_jira.verified_tokens)
        self.assertIsNone(self.db.get_user_jira_settings("ivan@example.com"))

    def test_help_mentions_pat_login_and_charts(self):
        result = self.run_command("help", _FakeUserJiraClient())

        self.assertIn("login <PAT>", result)
        self.assertIn("графики PROJECT_KEY", result)
        self.assertNotIn("password", result)

    def test_charts_alias_routes_to_analytics(self):
        result = self.run_command("графики", _FakeUserJiraClient())
        self.assertIn("Укажите ключ проекта", result)


class TestMaskSecrets(unittest.TestCase):
    def test_masks_token_after_login_command(self):
        self.assertEqual("login ***", mask_secrets(f"login {TOKEN}"))
        self.assertEqual("@jora войти ***", mask_secrets("@jora войти short"))

    def test_masks_token_like_strings(self):
        self.assertEqual("look ***", mask_secrets(f"look {TOKEN}"))

    def test_keeps_regular_commands(self):
        self.assertEqual("графики IDB", mask_secrets("графики IDB"))


if __name__ == "__main__":
    unittest.main()
