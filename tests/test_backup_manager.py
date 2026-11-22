import json
import csv
import pytest
from datetime import date, timedelta
from core.database import DatabaseManager
from core.backup_manager import (
    export_payments_csv,
    export_rooms_status_csv,
    export_database_to_json,
    import_database_from_json,
    is_backup_overdue,
    record_backup_completed,
    get_last_backup_date,
    build_backup_reminder_whatsapp_message,
    get_operator_backup_whatsapp_link
)


@pytest.fixture
def populated_db():
    db = DatabaseManager(":memory:")
    # Create rooms
    r1 = db.create_room("Cuarto 101", 2800.0)
    r2 = db.create_room("Cuarto 102", 3200.0)
    r3 = db.create_room("Cuarto 103", 2500.0)

    # Start leases
    l1 = db.start_lease(r1.id, "Ana Gómez", "5215512345678", 2800.0, "2026-01-01")
    l2 = db.start_lease(r2.id, "Betina Ruiz", "5215587654321", 3200.0, "2026-03-01")

    # Record payments
    db.record_payment(l1.id, 2026, 11, 2800.0, "2026-11-02")
    db.record_payment(l2.id, 2026, 10, 3200.0, "2026-10-04")

    # Settings
    db.set_setting("app_name", "renTalo")
    return db


def test_export_payments_csv_utf8_sig(populated_db, tmp_path):
    csv_file = tmp_path / "pagos.csv"
    export_payments_csv(populated_db, csv_file)

    assert csv_file.exists()
    raw_bytes = csv_file.read_bytes()
    # Check UTF-8 BOM
    assert raw_bytes.startswith(b"\xef\xbb\xbf")

    # Read as text with utf-8-sig
    with open(csv_file, mode="r", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        header = next(reader)
        # Verify Spanish headers
        assert "ID Pago" in header
        assert "Cuarto" in header
        assert "Inquilino" in header
        assert "Año" in header
        assert "Mes" in header
        assert "Monto" in header

        rows = list(reader)
        assert len(rows) == 2


def test_export_rooms_status_csv_utf8_sig(populated_db, tmp_path):
    csv_file = tmp_path / "estado_cuartos.csv"
    ref_date = date(2026, 11, 4)
    export_rooms_status_csv(populated_db, csv_file, reference_date=ref_date)

    assert csv_file.exists()
    assert csv_file.read_bytes().startswith(b"\xef\xbb\xbf")

    with open(csv_file, mode="r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        assert len(rows) == 3

        # Room 101 is paid for November
        r101 = next(r for r in rows if r["Cuarto"] == "Cuarto 101")
        assert r101["Estado"] == "Ocupado"
        assert r101["Estatus Renta"] == "PAGADO"
        assert r101["Inquilino"] == "Ana Gómez"

        # Room 102 has no Nov payment, on day 4 -> PENDIENTE
        r102 = next(r for r in rows if r["Cuarto"] == "Cuarto 102")
        assert r102["Estado"] == "Ocupado"
        assert r102["Estatus Renta"] == "PENDIENTE"

        # Room 103 is vacant -> Disponible
        r103 = next(r for r in rows if r["Cuarto"] == "Cuarto 103")
        assert r103["Estado"] == "Disponible"
        assert r103["Inquilino"] == "-"


def test_json_backup_and_restore_roundtrip(populated_db, tmp_path):
    json_file = tmp_path / "backup_rentalo.json"
    export_database_to_json(populated_db, json_file)

    assert json_file.exists()
    with open(json_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data["app"] in ["renTalo", "RentaFácil"]
    assert "rooms" in data and len(data["rooms"]) == 3
    assert "leases" in data and len(data["leases"]) == 2
    assert "payments" in data and len(data["payments"]) == 2
    assert "settings" in data

    # Restore into a fresh database
    new_db = DatabaseManager(":memory:")
    assert len(new_db.get_all_rooms()) == 0

    success = import_database_from_json(new_db, json_file)
    assert success is True

    # Verify restored records
    restored_rooms = new_db.get_all_rooms()
    assert len(restored_rooms) == 3

    restored_leases = new_db.get_all_leases(active_only=False)
    assert len(restored_leases) == 2

    restored_payments = new_db.get_all_payments()
    assert len(restored_payments) == 2

    assert new_db.get_setting("app_name") in ["renTalo", "RentaFácil"]


def test_json_import_corrupted_data_rolls_back(populated_db, tmp_path):
    bad_json_file = tmp_path / "corrupted_backup.json"
    # Malformed data missing critical fields
    bad_json_file.write_text('{"app": "renTalo", "rooms": [{"invalid_key": 1}]}', encoding="utf-8")

    # Attempt to import into populated db should fail and keep original data intact
    with pytest.raises(Exception):
        import_database_from_json(populated_db, bad_json_file)

    # Populated db must still have original 3 rooms
    assert len(populated_db.get_all_rooms()) == 3


def test_backup_overdue_check_never_backed_up(populated_db):
    ref_date = date(2026, 11, 22)
    # Never backed up -> overdue is True
    assert is_backup_overdue(populated_db, ref_date, days=180) is True
    assert get_last_backup_date(populated_db) is None


def test_backup_overdue_check_with_dates(populated_db):
    ref_date = date(2026, 11, 22)

    # Backed up 100 days ago -> False
    record_backup_completed(populated_db, ref_date - timedelta(days=100))
    assert is_backup_overdue(populated_db, ref_date, days=180) is False
    assert get_last_backup_date(populated_db) == (ref_date - timedelta(days=100)).isoformat()

    # Backed up 180 days ago -> True
    record_backup_completed(populated_db, ref_date - timedelta(days=180))
    assert is_backup_overdue(populated_db, ref_date, days=180) is True

    # Backed up 200 days ago -> True
    record_backup_completed(populated_db, ref_date - timedelta(days=200))
    assert is_backup_overdue(populated_db, ref_date, days=180) is True


def test_backup_reminder_whatsapp_message_and_link(populated_db):
    msg = build_backup_reminder_whatsapp_message(operator_name="Don José", days_since_last=185)
    assert "Don José" in msg
    assert "respaldo" in msg.lower()
    assert "185" in msg or "6 meses" in msg

    phone = "5215599887766"
    link = get_operator_backup_whatsapp_link(phone, msg)
    assert link.startswith("https://wa.me/5215599887766?text=")
    assert "respaldo" in link.lower() or "respaldo" in link


def test_merge_database_from_json_multi_supervisor(tmp_path):
    from core.backup_manager import merge_database_from_json

    # Supervisor A DB
    db_a = DatabaseManager(":memory:")
    r1 = db_a.create_room("Cuarto 101", 2500.0)
    l1 = db_a.start_lease(r1.id, "Carlos A", "5215511111111", 2500.0, "2026-01-01")
    db_a.record_payment(l1.id, 2026, 11, 2500.0, "2026-11-02")

    # Supervisor B DB
    db_b = DatabaseManager(":memory:")
    r2 = db_b.create_room("Cuarto 102", 3000.0)
    l2 = db_b.start_lease(r2.id, "Diana B", "5215522222222", 3000.0, "2026-01-01")
    db_b.record_payment(l2.id, 2026, 11, 3000.0, "2026-11-03")

    # Export Supervisor B's database to JSON
    json_b_path = tmp_path / "supervisor_b_export.json"
    export_database_to_json(db_b, json_b_path)

    # Supervisor A imports/merges Supervisor B's JSON without wiping out Supervisor A's work
    stats = merge_database_from_json(db_a, json_b_path)
    assert stats["success"] is True

    # Supervisor A now has BOTH rooms, BOTH leases, and BOTH payments
    all_rooms = db_a.get_all_rooms()
    assert len(all_rooms) == 2
    room_names = [r.name for r in all_rooms]
    assert "Cuarto 101" in room_names
    assert "Cuarto 102" in room_names

    all_leases = db_a.get_all_leases()
    assert len(all_leases) == 2

    all_payments = db_a.get_all_payments()
    assert len(all_payments) == 2


