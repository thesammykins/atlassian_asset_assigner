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


def test_bulk_assignee_flow_with_mocks(monkeypatch):
    def fake_get(self, url, params=None, **kwargs):
        # Schemas list
        if "/objectschema/list" in url:
            return FakeResponse(json_data={"values": [{"id": 100, "name": "Hardware"}]})
        # Object types for Hardware
        if "/objectschema/100/objecttypes" in url:
            return FakeResponse(json_data={"values": [{"id": 28, "name": "Laptops"}]})
        # Object type attributes (Assignee exists)
        if "/objecttype/28/attributes" in url:
            return FakeResponse(json_data=[{"id": 555, "name": "Assignee"}])
        # Asset by key lookups for full object data
        if url.endswith("/object/HW-100") or url.endswith("None/object/HW-100"):
            return FakeResponse(
                json_data={
                    "id": 1000,
                    "objectKey": "HW-100",
                    "objectType": {"id": 28, "name": "Laptops"},
                    "attributes": [
                        {
                            "objectTypeAttribute": {"name": "User Email"},
                            "objectAttributeValues": [{"displayValue": "alice@example.com"}],
                        }
                        # No Assignee attribute
                    ],
                }
            )
        if url.endswith("/object/HW-101") or url.endswith("None/object/HW-101"):
            return FakeResponse(
                json_data={
                    "id": 1010,
                    "objectKey": "HW-101",
                    "objectType": {"id": 28, "name": "Laptops"},
                    "attributes": []  # No User Email
                }
            )
        if url.endswith("/object/HW-102") or url.endswith("None/object/HW-102"):
            return FakeResponse(
                json_data={
                    "id": 1020,
                    "objectKey": "HW-102",
                    "objectType": {"id": 28, "name": "Laptops"},
                    "attributes": [
                        {
                            "objectTypeAttribute": {"name": "User Email"},
                            "objectAttributeValues": [{"displayValue": "bob@example.com"}],
                        },
                        {
                            "objectTypeAttribute": {"name": "Assignee"},
                            "objectAttributeValues": [{"displayValue": "acc-bob"}],
                        },
                    ],
                }
            )
        # Jira user search
        if url.endswith("/rest/api/3/user/search"):
            q = (params or {}).get("query", "").lower()
            # Return a single exact match user
            account = {
                "alice@example.com": "acc-alice",
                "bob@example.com": "acc-bob",
            }.get(q, "acc-unknown")
            return FakeResponse(
                json_data=[
                    {
                        "accountId": account,
                        "emailAddress": q,
                        "displayName": q.split("@")[0].title(),
                        "accountType": "atlassian",
                        "active": True,
                    }
                ]
            )
        # Jira user validation (by accountId)
        if url.endswith("/rest/api/3/user"):
            return FakeResponse(json_data={"active": True})
        return FakeResponse(status_code=404, json_data={"message": "not found"})

    def fake_post(self, url, json=None, params=None, **kwargs):
        # AQL: return three candidate laptop objects by key
        if url.endswith("/object/aql") or url.endswith("None/object/aql"):
            return FakeResponse(json_data={"values": [
                {"objectKey": "HW-100"}, {"objectKey": "HW-101"}, {"objectKey": "HW-102"}
            ]})
        return FakeResponse(status_code=404, json_data={"message": "not found"})

    import requests

    monkeypatch.setattr(requests.Session, "get", fake_get, raising=True)
    monkeypatch.setattr(requests.Session, "post", fake_post, raising=True)

    asset_manager_mod = importlib.import_module("src.asset_manager")

    manager = asset_manager_mod.AssetManager()

    # Discover candidates via AQL
    candidates = manager.get_hardware_laptops_objects()
    assert [c.get("objectKey") for c in candidates] == ["HW-100", "HW-101", "HW-102"]

    # Filter to those needing processing (should include only HW-100)
    to_process = manager.filter_objects_for_processing(candidates)
    keys = [o.get("objectKey") for o in to_process]
    assert keys == ["HW-100"]

    # Process HW-100 in dry run: should prepare update to acc-alice
    res = manager.process_asset("HW-100", dry_run=True)
    assert res["success"] is True
    assert res["skipped"] is False
    assert res["new_assignee"] == "acc-alice"
    assert res["updated"] is False

    # Process HW-101: should skip due to missing user email
    res2 = manager.process_asset("HW-101", dry_run=True)
    assert res2["success"] is False
    assert res2["skipped"] is True
    assert "No '" in (res2.get("skip_reason") or "")

    # Process HW-102: should skip due to already assigned
    res3 = manager.process_asset("HW-102", dry_run=True)
    assert res3["success"] is False
    assert res3["skipped"] is True
    assert res3["skip_reason"].startswith("Assignee already set to")

