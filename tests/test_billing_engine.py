import pytest
from datetime import date
from core.models import Lease, Payment
from core.billing_engine import (
    get_payment_status,
    STATUS_PAGADO,
    STATUS_PENDIENTE,
    STATUS_ATRASADO,
    get_spanish_month_name,
    build_payment_reminder_message,
    generate_whatsapp_link,
    get_whatsapp_payment_link
)


@pytest.fixture
def sample_lease():
    return Lease(
        id=1,
        room_id=10,
        tenant_name="Carlos Sánchez",
        tenant_phone="5215512345678",
        monthly_rent=3200.0,
        start_date="2026-01-01",
        end_date=None,
        is_active=True
    )


def test_payment_status_paid(sample_lease):
    # Payment exists for the current month
    payments = [
        Payment(id=1, lease_id=sample_lease.id, billing_year=2026, billing_month=11, amount=3200.0, paid_date="2026-11-02")
    ]
    ref_date = date(2026, 11, 4)
    assert get_payment_status(sample_lease, payments, ref_date) == STATUS_PAGADO

    # Even on day 6 or later, if paid, it is PAGADO
    assert get_payment_status(sample_lease, payments, date(2026, 11, 10)) == STATUS_PAGADO


def test_payment_status_pending_window_edge_cases(sample_lease):
    payments = []

    # Day 1: Due date, within 5-day window -> PENDIENTE
    assert get_payment_status(sample_lease, payments, date(2026, 11, 1)) == STATUS_PENDIENTE

    # Day 3: Within 5-day window -> PENDIENTE
    assert get_payment_status(sample_lease, payments, date(2026, 11, 3)) == STATUS_PENDIENTE

    # Day 5: Last day of the 5 natural days window -> PENDIENTE
    assert get_payment_status(sample_lease, payments, date(2026, 11, 5)) == STATUS_PENDIENTE


def test_payment_status_overdue_edge_cases(sample_lease):
    payments = []

    # Day 6: Past the 5-day window -> ATRASADO
    assert get_payment_status(sample_lease, payments, date(2026, 11, 6)) == STATUS_ATRASADO

    # Day 25: Past the 5-day window -> ATRASADO
    assert get_payment_status(sample_lease, payments, date(2026, 11, 25)) == STATUS_ATRASADO


def test_payment_status_different_month_does_not_count(sample_lease):
    # Only October payment exists, checking for November
    payments = [
        Payment(id=1, lease_id=sample_lease.id, billing_year=2026, billing_month=10, amount=3200.0, paid_date="2026-10-02")
    ]
    # In November day 2 -> PENDIENTE (since Nov is not paid)
    assert get_payment_status(sample_lease, payments, date(2026, 11, 2)) == STATUS_PENDIENTE
    # In November day 7 -> ATRASADO (since Nov is not paid)
    assert get_payment_status(sample_lease, payments, date(2026, 11, 7)) == STATUS_ATRASADO


def test_spanish_month_name():
    assert get_spanish_month_name(1) == "enero"
    assert get_spanish_month_name(5) == "mayo"
    assert get_spanish_month_name(11) == "noviembre"
    assert get_spanish_month_name(12) == "diciembre"


def test_build_payment_reminder_message_pending():
    msg = build_payment_reminder_message(
        tenant_name="Carlos Sánchez",
        room_name="Cuarto 2",
        year=2026,
        month=11,
        amount=3200.0,
        status=STATUS_PENDIENTE
    )
    assert "Carlos Sánchez" in msg
    assert "Cuarto 2" in msg
    assert "noviembre" in msg
    assert "2026" in msg
    assert "3,200.00" in msg or "3200" in msg
    # Should be friendly, natural Spanish
    assert "renta" in msg.lower()


def test_build_payment_reminder_message_overdue():
    msg = build_payment_reminder_message(
        tenant_name="Carlos Sánchez",
        room_name="Cuarto 2",
        year=2026,
        month=11,
        amount=3200.0,
        status=STATUS_ATRASADO
    )
    assert "Carlos Sánchez" in msg
    assert "Cuarto 2" in msg
    assert "noviembre" in msg
    assert "2026" in msg
    # Must note that the 5-day window has passed politely
    assert "5 días" in msg or "cinco días" in msg


def test_generate_whatsapp_link():
    phone = "+52 1 (55) 1234-5678"
    raw_message = "Hola Carlos, tu renta de noviembre es de $3,200. ¡Gracias!"
    url = generate_whatsapp_link(phone, raw_message)

    # Phone is normalized to digits only
    assert url.startswith("https://wa.me/5215512345678?text=")
    # Accents and special chars are URL encoded
    assert "%20" in url or "+" in url
    assert "!" not in url.split("text=")[1] or "%21" in url


def test_get_whatsapp_payment_link(sample_lease):
    ref_date = date(2026, 11, 2)
    url = get_whatsapp_payment_link(
        lease=sample_lease,
        room_name="Cuarto 2",
        reference_date=ref_date,
        amount=3200.0,
        status=STATUS_PENDIENTE
    )
    assert url.startswith("https://wa.me/5215512345678?text=")
    assert "Carlos" in url or "Carlos%20S%C3%A1nchez" in url

