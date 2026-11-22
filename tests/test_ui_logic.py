import pytest
from datetime import date, timedelta
from core.database import DatabaseManager
from core.models import Room, Lease, Payment
from core.billing_engine import (
    STATUS_PAGADO,
    STATUS_PENDIENTE,
    STATUS_ATRASADO
)
from core.backup_manager import is_backup_overdue, record_backup_completed
from ui.theme_config import (
    COLOR_PAGADO,
    COLOR_PENDIENTE,
    COLOR_ATRASADO,
    COLOR_DISPONIBLE,
    get_status_theme,
    STATUS_DISPONIBLE
)


def test_status_theme_colors():
    theme_pagado = get_status_theme(STATUS_PAGADO)
    assert theme_pagado["color"] == COLOR_PAGADO
    assert theme_pagado["label"] == "PAGADO"
    assert "check" in theme_pagado["icon"]

    theme_pendiente = get_status_theme(STATUS_PENDIENTE)
    assert theme_pendiente["color"] == COLOR_PENDIENTE
    assert theme_pendiente["label"] == "PENDIENTE"
    assert "clock" in theme_pendiente["icon"] or "alert" in theme_pendiente["icon"]

    theme_atrasado = get_status_theme(STATUS_ATRASADO)
    assert theme_atrasado["color"] == COLOR_ATRASADO
    assert theme_atrasado["label"] == "ATRASADO"
    assert "alert" in theme_atrasado["icon"]

    theme_disponible = get_status_theme(STATUS_DISPONIBLE)
    assert theme_disponible["color"] == COLOR_DISPONIBLE
    assert theme_disponible["label"] == "DISPONIBLE"


def test_backup_banner_state_logic():
    db = DatabaseManager(":memory:")
    today = date(2026, 11, 22)

    # Initial state: never backed up -> Banner must be visible
    assert is_backup_overdue(db, reference_date=today, days=180) is True

    # After backing up today -> Banner must be hidden
    record_backup_completed(db, today)
    assert is_backup_overdue(db, reference_date=today, days=180) is False

    # After 179 days -> Still hidden
    assert is_backup_overdue(db, reference_date=today + timedelta(days=179), days=180) is False

    # After 180 days -> Banner must be visible again
    assert is_backup_overdue(db, reference_date=today + timedelta(days=180), days=180) is True

