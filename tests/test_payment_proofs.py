import pytest
import csv
from datetime import date
from core.database import DatabaseManager
from core.models import Room, Lease, Payment
from core.backup_manager import (
    export_payments_csv,
    export_database_to_json,
    import_database_from_json,
    merge_database_from_json
)
from ui.android_bridge import save_payment_proof


@pytest.fixture
def db_with_lease():
    db = DatabaseManager(":memory:")
    room = db.create_room("Cuarto 201", 3500.0)
    lease = db.start_lease(
        room_id=room.id,
        tenant_name="Esteban Morales",
        tenant_phone="5215512345678",
        monthly_rent=3500.0,
        start_date="2026-01-01"
    )
    return db, room, lease


def test_record_payment_with_proof_image_and_method(db_with_lease):
    db, room, lease = db_with_lease

    # Record payment with transfer proof image
    payment = db.record_payment(
        lease_id=lease.id,
        billing_year=2026,
        billing_month=11,
        amount=3500.0,
        paid_date="2026-11-03",
        proof_image_path="comprobantes_pagos/pago_1_2026_11.jpg",
        payment_method="TRANSFERENCIA"
    )

    assert payment.id is not None
    assert payment.proof_image_path == "comprobantes_pagos/pago_1_2026_11.jpg"
    assert payment.payment_method == "TRANSFERENCIA"

    # Retrieve from DB
    retrieved = db.get_payment(lease.id, 2026, 11)
    assert retrieved is not None
    assert retrieved.proof_image_path == "comprobantes_pagos/pago_1_2026_11.jpg"
    assert retrieved.payment_method == "TRANSFERENCIA"


def test_idempotent_payment_update_proof(db_with_lease):
    db, room, lease = db_with_lease

    # Initial payment in cash without proof
    db.record_payment(
        lease_id=lease.id,
        billing_year=2026,
        billing_month=11,
        amount=3500.0,
        paid_date="2026-11-03",
        proof_image_path=None,
        payment_method="EFECTIVO"
    )

    # Re-recording or updating with a transfer screenshot
    updated = db.record_payment(
        lease_id=lease.id,
        billing_year=2026,
        billing_month=11,
        amount=3500.0,
        paid_date="2026-11-03",
        proof_image_path="comprobantes_pagos/spei_bbva_11.png",
        payment_method="TRANSFERENCIA"
    )

    assert updated.proof_image_path == "comprobantes_pagos/spei_bbva_11.png"
    assert updated.payment_method == "TRANSFERENCIA"

    payments = db.get_payments_for_lease(lease.id)
    assert len(payments) == 1
    assert payments[0].proof_image_path == "comprobantes_pagos/spei_bbva_11.png"


def test_export_payments_csv_includes_method_and_proof(db_with_lease, tmp_path):
    db, room, lease = db_with_lease
    db.record_payment(
        lease_id=lease.id,
        billing_year=2026,
        billing_month=11,
        amount=3500.0,
        paid_date="2026-11-03",
        proof_image_path="comprobantes_pagos/pago_11.jpg",
        payment_method="TRANSFERENCIA"
    )

    csv_path = tmp_path / "pagos_con_comprobante.csv"
    export_payments_csv(db, csv_path)

    with open(csv_path, mode="r", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        header = next(reader)
        assert "Método" in header
        assert "Comprobante" in header

        row = next(reader)
        assert "TRANSFERENCIA" in row
        # Check proof indicator
        assert any("pago_11.jpg" in col or "Sí" in col for col in row)


def test_backup_json_roundtrip_preserves_proof_image(db_with_lease, tmp_path):
    db, room, lease = db_with_lease
    db.record_payment(
        lease_id=lease.id,
        billing_year=2026,
        billing_month=11,
        amount=3500.0,
        paid_date="2026-11-03",
        proof_image_path="comprobantes_pagos/spei_folio_9921.jpg",
        payment_method="TRANSFERENCIA"
    )

    json_path = tmp_path / "backup_proof.json"
    export_database_to_json(db, json_path)

    new_db = DatabaseManager(":memory:")
    import_database_from_json(new_db, json_path)

    restored_payment = new_db.get_payment(lease.id, 2026, 11)
    assert restored_payment is not None
    assert restored_payment.proof_image_path == "comprobantes_pagos/spei_folio_9921.jpg"
    assert restored_payment.payment_method == "TRANSFERENCIA"


def test_merge_preserves_payment_proof(tmp_path):
    # Supervisor A DB
    db_a = DatabaseManager(":memory:")
    r1 = db_a.create_room("Cuarto 1", 2000.0)
    l1 = db_a.start_lease(r1.id, "Carlos", "521551", 2000.0, "2026-01-01")

    # Supervisor B records payment with proof
    db_b = DatabaseManager(":memory:")
    r1_b = db_b.create_room("Cuarto 1", 2000.0)
    l1_b = db_b.start_lease(r1_b.id, "Carlos", "521551", 2000.0, "2026-01-01")
    db_b.record_payment(
        lease_id=l1_b.id,
        billing_year=2026,
        billing_month=11,
        amount=2000.0,
        paid_date="2026-11-02",
        proof_image_path="comprobantes_pagos/transfer_carlos_nov.jpg",
        payment_method="TRANSFERENCIA"
    )

    export_path = tmp_path / "b_export.json"
    export_database_to_json(db_b, export_path)

    merge_database_from_json(db_a, export_path)

    merged_payment = db_a.get_payment(l1.id, 2026, 11)
    assert merged_payment is not None
    assert merged_payment.proof_image_path == "comprobantes_pagos/transfer_carlos_nov.jpg"
    assert merged_payment.payment_method == "TRANSFERENCIA"


def test_save_payment_proof_storage(tmp_path):
    # Create dummy source image file
    source_img = tmp_path / "screenshot_spei.png"
    source_img.write_bytes(b"dummy_image_data")

    # Save to managed app directory
    saved_rel_path = save_payment_proof(
        source_path=str(source_img),
        lease_id=10,
        year=2026,
        month=11
    )

    assert "comprobantes_pagos" in saved_rel_path
    assert "10_2026_11" in saved_rel_path

