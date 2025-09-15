import importlib
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


def test_retirement_flow_with_mocks(monkeypatch):
    def fake_get(self, url, params=None, **kwargs):
        # Schemas list (allow query params or missing base)
        if "/objectschema/list" in url:
            return FakeResponse(json_data={"values": [{"id": 100, "name": "Hardware"}]})
        # Object types for Hardware
        if "/objectschema/100/objecttypes" in url:
            return FakeResponse(json_data={"values": [{"id": 28, "name": "Laptops"}]})
        # AQL queries
        if url.endswith("/object/aql"):
            # Return one laptop candidate
            return FakeResponse(json_data={"values": [{"objectKey": "HW-493"}]})
        # Asset by key
        if url.endswith("/object/HW-493") or url.endswith("None/object/HW-493"):
            return FakeResponse(
                json_data={
                    "id": 1493,
                    "objectKey": "HW-493",
                    "objectType": {"id": 28, "name": "Laptops"},
                    "attributes": [
                        {
                            "objectTypeAttribute": {"name": "Retirement Date"},
                            "objectAttributeValues": [{"displayValue": "2024-01-01"}],
                        },
                        {
                            "objectTypeAttribute": {"name": "Asset Status"},
                            "objectAttributeValues": [{"displayValue": "In Use"}],
                        },
                    ],
                }
            )
        return FakeResponse(status_code=404, json_data={"message": "not found"})

    import requests

    monkeypatch.setattr(requests.Session, "get", fake_get, raising=True)

    def fake_post(self, url, json=None, params=None, **kwargs):
        # AQL endpoint uses POST with payload
        if url.endswith("/object/aql") or url.endswith("None/object/aql"):
            return FakeResponse(json_data={"values": [{"objectKey": "HW-493"}]})
        return FakeResponse(status_code=404, json_data={"message": "not found"})

    monkeypatch.setattr(requests.Session, "post", fake_post, raising=True)

    asset_mod = importlib.import_module("src.asset_manager")

    manager = asset_mod.AssetManager()

    # Single retirement processing (dry run)
    single = manager.process_retirement("HW-493", dry_run=True)
    assert single["success"] is True
    assert single["retirement_date"] == "2024-01-01"
    assert single["current_status"] == "In Use"
    assert single["new_status"] == "Retired"
    assert single["updated"] is False

    # Bulk discovery flows
    all_objs = manager.get_assets_pending_retirement()
    assert isinstance(all_objs, list)
    assert any(o.get("objectKey") == "HW-493" for o in all_objs)
