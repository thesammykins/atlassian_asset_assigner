from typing import Any, Dict


def _sample_object_with_attrs() -> Dict[str, Any]:
    return {
        "attributes": [
            {
                "objectTypeAttribute": {"name": "User Email"},
                "objectAttributeValues": [{"displayValue": "user@example.com"}],
            },
            {
                "objectTypeAttribute": {"name": "Tags"},
                "objectAttributeValues": [
                    {"displayValue": "alpha"},
                    {"displayValue": "beta"},
                ],
            },
        ]
    }


def test_extract_attribute_value_simple():
    from src.jira_assets_client import JiraAssetsClient

    client = JiraAssetsClient()
    obj = _sample_object_with_attrs()
    assert client.extract_attribute_value(obj, "User Email") == "user@example.com"
    assert client.extract_attribute_value(obj, "Tags") == ["alpha", "beta"]
    assert client.extract_attribute_value(obj, "Missing") is None


def test_create_attribute_update_uses_attribute_id(monkeypatch):
    from src.jira_assets_client import JiraAssetsClient

    client = JiraAssetsClient()

    # Mock attributes lookup to avoid network
    def fake_get_object_attributes(object_type_id: int):
        return [
            {"id": 999, "name": "Assignee"},
            {"id": 123, "name": "Other"},
        ]

    monkeypatch.setattr(client, "get_object_attributes", fake_get_object_attributes)

    update = client.create_attribute_update("Assignee", "7123:accountid", 42)
    assert update["objectTypeAttributeId"] == 999
    assert update["objectAttributeValues"][0]["value"] == "7123:accountid"

