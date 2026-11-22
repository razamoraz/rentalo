import pytest
from datetime import date
from core.database import DatabaseManager
from core.models import Room, Lease, Payment
from core.billing_engine import (
    calculate_proportional_rent,
    build_welcome_lease_message
)
from core.backup_manager import (
    export_rooms_status_csv,
    export_database_to_json,
    import_database_from_json
)


def test_calculate_proportional_rent_first_5_days():
    # If starting on day 1 to 5, charge standard full month
    rent = 3000.0
    assert calculate_proportional_rent(rent, date(2026, 11, 1)) == 3000.0
    assert calculate_proportional_rent(rent, date(2026, 11, 5)) == 3000.0


def test_calculate_proportional_rent_after_day_5():
    # November has 30 days. If starting November 16:
    # Remaining days: 30 - 16 + 1 = 15 days (exactly half the month)
    # Rent = 3000.0 -> Proportional = 1500.0
    rent = 3000.0
    prop_rent = calculate_proportional_rent(rent, date(2026, 11, 16))
    assert prop_rent == 1500.0

    # November 18 (13 days remaining):
    # 3000 / 30 * 13 = 1300.0
    assert calculate_proportional_rent(rent, date(2026, 11, 18)) == 1300.0

    # Test month with 31 days (e.g. December 22)
    # 31 - 22 + 1 = 10 days remaining
    # 3100 / 31 * 10 = 1000.0
    assert calculate_proportional_rent(3100.0, date(2026, 12, 22)) == 1000.0


def test_start_lease_with_deposit_and_proportional_rent():
    db = DatabaseManager(":memory:")
    room = db.create_room("Cuarto 105", 3000.0)

    start_d = "2026-11-18"
    prop_rent = calculate_proportional_rent(3000.0, date(2026, 11, 18))

    lease = db.start_lease(
        room_id=room.id,
        tenant_name="Mariana Castillo",
        tenant_phone="5215512345678",
        monthly_rent=3000.0,
        start_date=start_d,
        deposit_amount=3000.0,
        initial_rent=prop_rent
    )

    assert lease.id is not None
    assert lease.deposit_amount == 3000.0
    assert lease.initial_rent == 1300.0

    # Retrieve from db
    saved_lease = db.get_lease(lease.id)
    assert saved_lease.deposit_amount == 3000.0
    assert saved_lease.initial_rent == 1300.0


def test_welcome_message_includes_deposit_and_proportional_rent():
    msg = build_welcome_lease_message(
        tenant_name="Mariana Castillo",
        room_name="Cuarto 105",
        start_date="2026-11-18",
        monthly_rent=3000.0,
        deposit_amount=3000.0,
        first_month_rent=1300.0
    )

    assert "Mariana Castillo" in msg
    assert "Cuarto 105" in msg
    assert "3,000.00" in msg or "3000" in msg
    assert "1,300.00" in msg or "1300" in msg
    assert "depósito" in msg.lower()
    assert "proporcional" in msg.lower()
    # Confirm the prohibited word is NOT in the template
    assert "prorrateo" not in msg.lower()
    assert "prorateo" not in msg.lower()


def test_csv_and_json_backup_preserves_deposit(tmp_path):
    db = DatabaseManager(":memory:")
    room = db.create_room("Cuarto 105", 3000.0)
    db.start_lease(
        room_id=room.id,
        tenant_name="Mariana Castillo",
        tenant_phone="5215512345678",
        monthly_rent=3000.0,
        start_date="2026-11-18",
        deposit_amount=3000.0,
        initial_rent=1300.0
    )

    # 1. Test CSV export includes Depósito
    csv_path = tmp_path / "cuartos.csv"
    export_rooms_status_csv(db, csv_path, reference_date=date(2026, 11, 20))
    csv_text = csv_path.read_text(encoding="utf-8-sig")
    assert "Depósito" in csv_text
    assert "3000.00" in csv_text

    # 2. Test JSON round-trip
    json_path = tmp_path / "backup.json"
    export_database_to_json(db, json_path)

    new_db = DatabaseManager(":memory:")
    import_database_from_json(new_db, json_path)

    restored_leases = new_db.get_all_leases()
    assert len(restored_leases) == 1
    assert restored_leases[0].deposit_amount == 3000.0
    assert restored_leases[0].initial_rent == 1300.0

