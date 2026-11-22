import os
import pytest
from datetime import date, timedelta
from main import RentaFacilApp
from core.billing_engine import STATUS_PAGADO, STATUS_PENDIENTE, STATUS_ATRASADO
from core.backup_manager import record_backup_completed
from ui.components import BackupWarningBanner, RoomCard


@pytest.fixture
def test_app(tmp_path):
    db_path = str(tmp_path / "test_app.db")
    app = RentaFacilApp(db_path=db_path)
    # Build widget tree
    app.build()
    return app


def test_app_initialization_and_sample_seed(test_app):
    assert test_app.db is not None
    rooms = test_app.db.get_all_rooms()
    assert len(rooms) >= 3

    # Check top bar
    assert test_app.top_bar.title.startswith("RentaFácil")
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
