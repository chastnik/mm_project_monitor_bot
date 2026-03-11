import sys
import types
import unittest
from unittest.mock import patch


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _FakeSession:
    def __init__(self, pages):
        self._pages = pages
        self.call_urls = []
        self.call_params = []

    def get(self, url, params=None):
        self.call_urls.append(url)
        self.call_params.append(params or {})
        start_at = (params or {}).get("startAt", 0)
        page = self._pages.get(start_at, {"values": [], "isLast": True})
        return _FakeResponse(page)


class _FakeJiraClient:
    def __init__(self, pages):
        self._options = {"server": "https://jira.example.com"}
        self._session = _FakeSession(pages)

    def projects(self):
        return []


class TestListProjectsPagination(unittest.TestCase):
    @patch.dict(
        sys.modules,
        {
            "mattermost_client": types.SimpleNamespace(mattermost_client=types.SimpleNamespace()),
            "scheduler": types.SimpleNamespace(scheduler=types.SimpleNamespace()),
        },
    )
    def test_list_projects_uses_project_search_and_fetches_all_pages(self):
        from bot_commands import BotCommandHandler

        first_page_values = [{"key": f"A{i:03d}", "name": f"Project A{i:03d}", "id": str(i)} for i in range(50)]
        second_page_values = [{"key": f"B{i:03d}", "name": f"Project B{i:03d}", "id": str(i)} for i in range(10)]
        fake_jira = _FakeJiraClient(
            {
                0: {"values": first_page_values, "isLast": False},
                50: {"values": second_page_values, "isLast": True},
            }
        )
        fake_user_jira_client = types.SimpleNamespace(get_jira_client=lambda _email: fake_jira)

        with patch.dict(
            sys.modules,
            {"user_jira_client": types.SimpleNamespace(user_jira_client=fake_user_jira_client)},
        ):
            result = BotCommandHandler().cmd_list_projects([], "user@example.com")

        self.assertIn("Доступные проекты в Jira (60)", result)
        self.assertEqual(2, len(fake_jira._session.call_urls))
        self.assertTrue(all(url.endswith("/rest/api/2/project/search") for url in fake_jira._session.call_urls))
        self.assertEqual(0, fake_jira._session.call_params[0]["startAt"])
        self.assertEqual(50, fake_jira._session.call_params[1]["startAt"])
