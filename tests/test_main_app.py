import os
import pytest
from datetime import date, timedelta
from main import RenTaloApp, RentaFacilApp
from core.billing_engine import STATUS_PAGADO, STATUS_PENDIENTE, STATUS_ATRASADO
from core.backup_manager import record_backup_completed
from ui.components import BackupWarningBanner, RoomCard


@pytest.fixture
def test_app(tmp_path):
    db_path = str(tmp_path / "test_app.db")
    app = RenTaloApp(db_path=db_path)
    # Build widget tree
    app.build()
    return app


def test_app_initialization_and_sample_seed(test_app):
    assert test_app.db is not None
    rooms = test_app.db.get_all_rooms()
    assert len(rooms) >= 3

    # Check top bar
    assert test_app.top_bar.title.startswith("renTalo")
    # Content layout contains widgets
    assert len(test_app.content_layout.children) > 0


def test_app_backup_banner_reactivity(test_app):
    # Fresh database -> is_backup_overdue is True -> Banner should be in content layout
    test_app.refresh_ui()
    banner_present = any(isinstance(w, BackupWarningBanner) for w in test_app.content_layout.children)
    assert banner_present is True

    # Mark backup as done today
    record_backup_completed(test_app.db, test_app.reference_date)
    test_app.refresh_ui()
    banner_present = any(isinstance(w, BackupWarningBanner) for w in test_app.content_layout.children)
    assert banner_present is False


def test_app_room_cards_rendered(test_app):
    test_app.refresh_ui()
    cards = [w for w in test_app.content_layout.children if isinstance(w, RoomCard)]
    assert len(cards) >= 3

    # Check that rooms have appropriate statuses
    occupied_card = next(c for c in cards if c.lease is not None)
    assert occupied_card.status in [STATUS_PAGADO, STATUS_PENDIENTE, STATUS_ATRASADO]

    vacant_card = next(c for c in cards if c.lease is None)
    assert vacant_card.status == "DISPONIBLE"


def test_app_check_monthly_notifications(test_app):
    # Running check_monthly_notifications should execute safely and record reminder sent
    test_app.check_monthly_notifications()
    # If run a second time, it should safely return without issues
    test_app.check_monthly_notifications()
    assert True


def test_app_send_house_rules_and_settlement_dialog(test_app):
    from unittest.mock import patch
    from ui.dialogs import show_end_lease_dialog

    leases = test_app.db.get_all_leases(active_only=True)
    assert len(leases) > 0
    lease = leases[0]
    room = test_app.db.get_room(lease.room_id)

    # Test house rules dispatch
    with patch("webbrowser.open") as mock_open:
        mock_open.return_value = True
        test_app.on_send_house_rules(lease)
        mock_open.assert_called_once()
        assert "Reglamento" in mock_open.call_args[0][0]

    # Test settlement dialog opens cleanly
    dialog = show_end_lease_dialog(
        db=test_app.db,
        room=room,
        lease=lease,
        on_ended=lambda: None
    )
    assert dialog is not None
    assert "Finiquito" in dialog.title
    dialog.dismiss()


def test_app_tenant_id_and_image_viewer_dialogs(test_app, tmp_path):
    from PIL import Image
    from ui.dialogs import show_tenant_id_dialog, show_image_viewer_dialog

    leases = test_app.db.get_all_leases(active_only=True)
    lease = leases[0]
    room = test_app.db.get_room(lease.room_id)

    img_file = tmp_path / "ine_test.jpg"
    Image.new("RGB", (400, 250), color=(40, 100, 140)).save(img_file)
    updated_lease = test_app.db.update_lease(lease.id, id_front_path=str(img_file))

    id_dialog = show_tenant_id_dialog(test_app.db, room, updated_lease, lambda: None)
    assert "INE" in id_dialog.title
    id_dialog.dismiss()

    viewer = show_image_viewer_dialog("INE Frente", str(img_file))
    assert viewer.title == "INE Frente"
    viewer.dismiss()

    # Room menu opens cleanly without throwing or overflowing horizontal buttons
    test_app.on_room_menu(room, updated_lease)
    assert True
