import pytest
from datetime import date
from core.models import Room, Lease, Payment
from core.database import DatabaseManager


@pytest.fixture
def db():
    # Use in-memory SQLite database with fresh schema for each test
    database = DatabaseManager(":memory:")
    return database


def test_create_and_get_room(db):
    room = db.create_room(name="Cuarto 1", default_rent=2500.0)
    assert room.id is not None
    assert room.name == "Cuarto 1"
    assert room.default_rent == 2500.0
    assert room.is_occupied is False

    retrieved = db.get_room(room.id)
    assert retrieved is not None
    assert retrieved.id == room.id
    assert retrieved.name == "Cuarto 1"
    assert retrieved.default_rent == 2500.0
    assert retrieved.is_occupied is False


def test_get_all_rooms(db):
    assert db.get_all_rooms() == []
    r1 = db.create_room("Cuarto 1", 2000.0)
    r2 = db.create_room("Cuarto 2", 3000.0)
    rooms = db.get_all_rooms()
    assert len(rooms) == 2
    assert [r.id for r in rooms] == [r1.id, r2.id]


def test_update_room(db):
    room = db.create_room("Cuarto 1", 2000.0)
    updated = db.update_room(room.id, name="Cuarto 1 - Planta Baja", default_rent=2200.0)
    assert updated.name == "Cuarto 1 - Planta Baja"
    assert updated.default_rent == 2200.0

    retrieved = db.get_room(room.id)
    assert retrieved.name == "Cuarto 1 - Planta Baja"
    assert retrieved.default_rent == 2200.0


def test_delete_room(db):
    room = db.create_room("Cuarto 1", 2000.0)
    assert db.delete_room(room.id) is True
    assert db.get_room(room.id) is None


def test_start_lease_marks_room_occupied(db):
    room = db.create_room("Cuarto 1", 2500.0)
    lease = db.start_lease(
        room_id=room.id,
        tenant_name="Juan Pérez",
        tenant_phone="5215512345678",
        monthly_rent=2500.0,
        start_date="2026-01-01"
    )

    assert lease.id is not None
    assert lease.room_id == room.id
    assert lease.tenant_name == "Juan Pérez"
    assert lease.tenant_phone == "5215512345678"
    assert lease.monthly_rent == 2500.0
    assert lease.start_date == "2026-01-01"
    assert lease.end_date is None
    assert lease.is_active is True

    # Room must now be marked occupied
    updated_room = db.get_room(room.id)
    assert updated_room.is_occupied is True


def test_start_lease_on_occupied_room_raises_error(db):
    room = db.create_room("Cuarto 1", 2500.0)
    db.start_lease(
        room_id=room.id,
        tenant_name="Juan Pérez",
        tenant_phone="5215512345678",
        monthly_rent=2500.0,
        start_date="2026-01-01"
    )

    # Trying to lease an already occupied room should fail
    with pytest.raises(ValueError, match="ocupado"):
        db.start_lease(
            room_id=room.id,
            tenant_name="María López",
            tenant_phone="5215587654321",
            monthly_rent=2500.0,
            start_date="2026-02-01"
        )


def test_end_lease_frees_room_and_preserves_history(db):
    room = db.create_room("Cuarto 1", 2500.0)
    lease = db.start_lease(
        room_id=room.id,
        tenant_name="Juan Pérez",
        tenant_phone="5215512345678",
        monthly_rent=2500.0,
        start_date="2026-01-01"
    )

    ended_lease = db.end_lease(lease.id, end_date="2026-06-30")
    assert ended_lease.is_active is False
    assert ended_lease.end_date == "2026-06-30"

    # Room is now free
    refreshed_room = db.get_room(room.id)
    assert refreshed_room.is_occupied is False

    # History is preserved
    all_leases = db.get_all_leases(active_only=False)
    assert len(all_leases) == 1
    assert all_leases[0].id == lease.id
    assert all_leases[0].is_active is False

    # Active lease query returns None
    assert db.get_active_lease_for_room(room.id) is None


def test_record_payment_idempotency(db):
    room = db.create_room("Cuarto 1", 2500.0)
    lease = db.start_lease(
        room_id=room.id,
        tenant_name="Juan Pérez",
        tenant_phone="5215512345678",
        monthly_rent=2500.0,
        start_date="2026-01-01"
    )

    # First payment confirmation
    p1 = db.record_payment(
        lease_id=lease.id,
        billing_year=2026,
        billing_month=11,
        amount=2500.0,
        paid_date="2026-11-03"
    )
    assert p1.id is not None
    assert p1.lease_id == lease.id
    assert p1.billing_year == 2026
    assert p1.billing_month == 11
    assert p1.amount == 2500.0
    assert p1.paid_date == "2026-11-03"

    # Second payment confirmation for the SAME month (idempotent)
    p2 = db.record_payment(
        lease_id=lease.id,
        billing_year=2026,
        billing_month=11,
        amount=2500.0,
        paid_date="2026-11-03"
    )

    payments = db.get_payments_for_lease(lease.id)
    assert len(payments) == 1
    assert payments[0].billing_year == 2026
    assert payments[0].billing_month == 11
    assert payments[0].amount == 2500.0


def test_record_payments_multiple_months(db):
    room = db.create_room("Cuarto 1", 2500.0)
    lease = db.start_lease(
        room_id=room.id,
        tenant_name="Juan Pérez",
        tenant_phone="5215512345678",
        monthly_rent=2500.0,
        start_date="2026-01-01"
    )

    db.record_payment(lease.id, 2026, 9, 2500.0, "2026-09-02")
    db.record_payment(lease.id, 2026, 10, 2500.0, "2026-10-04")
    db.record_payment(lease.id, 2026, 11, 2500.0, "2026-11-01")

    payments = db.get_payments_for_lease(lease.id)
    assert len(payments) == 3
    assert [p.billing_month for p in payments] == [9, 10, 11]


def test_settings_crud(db):
    assert db.get_setting("last_backup_date") is None
    assert db.get_setting("last_backup_date", default="nunca") == "nunca"

    db.set_setting("last_backup_date", "2026-05-01")
    assert db.get_setting("last_backup_date") == "2026-05-01"

    db.set_setting("last_backup_date", "2026-11-01")
    assert db.get_setting("last_backup_date") == "2026-11-01"


def test_update_lease(db):
    room = db.create_room("Cuarto 10", 2500.0)
    lease = db.start_lease(
        room_id=room.id,
        tenant_name="Juan Perez",
        tenant_phone="5215511112222",
        monthly_rent=2500.0,
        start_date="2026-01-01",
        deposit_amount=2500.0
    )

    # Operator corrects typo in tenant name, updates phone, adjusts rent and deposit
    updated = db.update_lease(
        lease_id=lease.id,
        tenant_name="Juan Carlos Pérez Gómez",
        tenant_phone="5215599998888",
        monthly_rent=2600.0,
        deposit_amount=2600.0
    )

    assert updated.tenant_name == "Juan Carlos Pérez Gómez"
    assert updated.tenant_phone == "5215599998888"
    assert updated.monthly_rent == 2600.0
    assert updated.deposit_amount == 2600.0
    assert updated.start_date == "2026-01-01"  # Unchanged

    # Verify persistence
    retrieved = db.get_lease(lease.id)
    assert retrieved.tenant_name == "Juan Carlos Pérez Gómez"
    assert retrieved.tenant_phone == "5215599998888"
    assert retrieved.monthly_rent == 2600.0
    assert retrieved.deposit_amount == 2600.0


