import pytest
from unittest.mock import patch
from ui.android_bridge import (
    clean_phone_for_whatsapp,
    open_whatsapp,
    share_file,
    get_export_directory
)


def test_clean_phone_for_whatsapp():
    assert clean_phone_for_whatsapp("+52 1 55 1234-5678") == "5215512345678"
    assert clean_phone_for_whatsapp("55 1234 5678") == "5215512345678" or clean_phone_for_whatsapp("55 1234 5678").endswith("5512345678")
    assert clean_phone_for_whatsapp("(55) 9876-5432") == "5215598765432" or clean_phone_for_whatsapp("(55) 9876-5432").endswith("5598765432")


def test_open_whatsapp_desktop_fallback():
    with patch("webbrowser.open") as mock_open:
        success = open_whatsapp("5215512345678", "Hola Carlos, recordatorio de renta")
        assert success is True
        mock_open.assert_called_once()
        args, _ = mock_open.call_args
        assert "https://wa.me/5215512345678" in args[0]
        assert "Carlos" in args[0] or "Carlos" in args[0].replace("%20", " ")


def test_share_file_fallback(tmp_path):
    test_file = tmp_path / "test_report.csv"
    test_file.write_text("ID,Cuarto,Monto", encoding="utf-8")

    # In non-android desktop environment, should successfully resolve path
    result = share_file(str(test_file), title="Compartir Reporte")
    assert result["success"] is True
    assert result["path"] == str(test_file)


def test_get_export_directory():
    export_dir = get_export_directory()
    assert export_dir.exists()
    assert export_dir.is_dir()

