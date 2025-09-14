from pathlib import Path


def test_get_processing_summary_groups_counts():
    from asset_manager import AssetManager

    manager = AssetManager()

    results = [
        {"success": True, "updated": True},
        {"success": True, "skipped": True, "skip_reason": "No email"},
        {"success": False, "error": "Asset HW-1 not found"},
        {"success": False, "error": "Permission denied: missing scope"},
        {"success": False, "error": "Hit rate limit 429"},
    ]

    summary = manager.get_processing_summary(results)
    assert summary["total_processed"] == 5
    assert summary["successful"] == 2
    assert summary["updated"] == 1
    assert summary["skipped"] == 1
    assert summary["errors"] == 3
    assert summary["skip_reasons"]["No email"] == 1
    assert summary["error_types"]["Not Found"] == 1
    assert summary["error_types"]["Permission Denied"] == 1
    assert summary["error_types"]["Rate Limited"] == 1


def test_parse_serial_numbers_from_csv_normalizes_and_dedupes(tmp_path: Path):
    from asset_manager import AssetManager

    p = tmp_path / "serials.csv"
    p.write_text(
        """SERIAL_NUMBER
 ab-123
AB-123

cd 456
""",
        encoding="utf-8",
    )

    manager = AssetManager()
    serials = manager.parse_serial_numbers_from_csv(str(p))
    # Normalized to uppercase, spaces removed, duplicates removed, original order preserved
    assert serials == ["AB-123", "CD456"]


def test_parse_serial_numbers_from_csv_missing_column(tmp_path: Path):
    import pytest

    from asset_manager import AssetManager, ValidationError

    p = tmp_path / "bad.csv"
    p.write_text("""SOMETHING_ELSE\nabc\n""", encoding="utf-8")

    manager = AssetManager()
    with pytest.raises(ValidationError):
        manager.parse_serial_numbers_from_csv(str(p))

