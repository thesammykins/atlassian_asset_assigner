import importlib
import os
from types import SimpleNamespace

import pytest


class FakeResponse:
    def __init__(self, status_code=200, json_data=None, text="", headers=None):
        self.status_code = status_code
        self._json = json_data if json_data is not None else {}
        self.text = text or ""
        self.headers = headers or {}

    @property
    def ok(self):
        return 200 <= self.status_code < 300

    def json(self):
        return self._json


@pytest.fixture(autouse=True)
def env(monkeypatch):
    # Minimal, non-placeholder config so import-time validation passes
    monkeypatch.setenv("JIRA_DOMAIN", "example.atlassian.net")
    monkeypatch.setenv("ASSETS_WORKSPACE_ID", "W1")
    monkeypatch.setenv("AUTH_METHOD", "basic")
    monkeypatch.setenv("JIRA_USER_EMAIL", "tester@example.com")
    monkeypatch.setenv("JIRA_API_TOKEN", "token-123")
    monkeypatch.setenv("LOG_TO_FILE", "false")
    yield


def test_single_laptop_flow_with_mocks(monkeypatch):
    # Mock all Session.get calls used by both clients
    def fake_get(self, url, params=None, **kwargs):
        # Asset by key
        if url.endswith("/object/HW-0002") or url.endswith("None/object/HW-0002"):
            return FakeResponse(
                json_data={
                    "id": 2002,
                    "objectKey": "HW-0002",
                    "label": "Test Laptop",
                    "objectType": {"id": 28, "name": "Laptops"},
                    "attributes": [
                        {
                            "objectTypeAttribute": {"name": "User Email"},
                            "objectAttributeValues": [{"displayValue": "jane.doe@example.com"}],
                        },
                        {
                            "objectTypeAttribute": {"name": "Assignee"},
                            "objectAttributeValues": [{"displayValue": "old-assignee@example.com"}],
                        },
                    ],
                }
            )
        # Attributes for object type
        if "/objecttype/28/attributes" in url:
            return FakeResponse(json_data=[{"id": 555, "name": "Assignee"}])
        # Jira user search
        if url.endswith("/rest/api/3/user/search"):
            q = (params or {}).get("query", "").lower()
            return FakeResponse(
                json_data=[
                    {
                        "accountId": "acc-123",
                        "emailAddress": q or "jane.doe@example.com",
                        "displayName": "Jane Doe",
                        "accountType": "atlassian",
                        "active": True,
                    }
                ]
            )
        # Jira user validation (by accountId)
        if url.endswith("/rest/api/3/user"):
            return FakeResponse(json_data={"active": True})
        return FakeResponse(status_code=404, json_data={"message": "not found"})

    # Patch requests.Session.get for the duration of this test
    import requests

    monkeypatch.setattr(requests.Session, "get", fake_get, raising=True)

    # Import modules after env + mocks are in place
    asset_mod = importlib.import_module("src.jira_assets_client")
    user_mod = importlib.import_module("src.jira_user_client")

    assets_client = asset_mod.JiraAssetsClient()
    user_client = user_mod.JiraUserClient()

    # Exercise flow similar to tests/test_single_laptop.py
    laptop = assets_client.get_object_by_key("HW-0002")
    user_email = assets_client.extract_attribute_value(laptop, "User Email")
    assignee = assets_client.extract_attribute_value(laptop, "Assignee")

    assert user_email == "jane.doe@example.com"
    assert assignee == "old-assignee@example.com"

    user_info = user_client.search_user_by_email(user_email)
    assert user_info["accountId"] == "acc-123"

    assert user_client.validate_account_id("acc-123") is True

    # Build attribute update for Assignee
    object_type_id = laptop["objectType"]["id"]
    update = assets_client.create_attribute_update("Assignee", "acc-123", object_type_id)
    assert update["objectTypeAttributeId"] == 555
    assert update["objectAttributeValues"][0]["value"] == "acc-123"

