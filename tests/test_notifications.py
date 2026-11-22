import pytest
from datetime import date
from core.database import DatabaseManager
from core.notifications import (
    get_monthly_reminder_status,
    mark_notification_sent,
    TYPE_PENDIENTE,
    TYPE_ATRASADO
)
from ui.android_bridge import send_local_notification


@pytest.fixture
def db_with_leases():
    db = DatabaseManager(":memory:")
    r1 = db.create_room("Cuarto 1", 2500.0)
    r2 = db.create_room("Cuarto 2", 3000.0)
    db.start_lease(r1.id, "Juan Pérez", "5215512345678", 2500.0, "2026-01-01")
    db.start_lease(r2.id, "María López", "5215587654321", 3000.0, "2026-01-01")
    return db


def test_reminder_notification_days_1_to_5_pending(db_with_leases):
    # Day 3: Within the 5 natural days payment window
    ref_date = date(2026, 11, 3)
    notification = get_monthly_reminder_status(db_with_leases, ref_date)

    assert notification is not None
    assert notification["type"] == TYPE_PENDIENTE
    assert "Cobro de Renta" in notification["title"] or "RentaFácil" in notification["title"]
    assert "noviembre" in notification["message"].lower()
    assert "2" in notification["message"]  # 2 pending rooms

    # After marking sent, should not notify again on same month and type
    mark_notification_sent(db_with_leases, ref_date, TYPE_PENDIENTE)
    assert get_monthly_reminder_status(db_with_leases, ref_date) is None


def test_reminder_notification_day_6_overdue(db_with_leases):
    # Day 7: Past the 5-day window -> Overdue reminder
    ref_date = date(2026, 11, 7)
    notification = get_monthly_reminder_status(db_with_leases, ref_date)

    assert notification is not None
    assert notification["type"] == TYPE_ATRASADO
    assert "Atrasada" in notification["title"] or "Atención" in notification["title"] or "Alerta" in notification["title"]
    assert "2" in notification["message"]  # 2 overdue rooms


def test_no_notification_when_all_paid(db_with_leases):
    ref_date = date(2026, 11, 2)
    # Record payments for both leases
    leases = db_with_leases.get_all_leases(active_only=True)
    for l in leases:
        db_with_leases.record_payment(l.id, 2026, 11, l.monthly_rent, "2026-11-01")

    # Since all are paid, no reminder needed
    notification = get_monthly_reminder_status(db_with_leases, ref_date)
    assert notification is None


def test_send_local_notification_fallback():
    # Test desktop/fallback dispatching
    result = send_local_notification(
        title="RentaFácil - Recordatorio",
        message="Tienes 2 cuartos pendientes de cobro este mes."
    )
    assert result is True

