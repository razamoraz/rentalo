import json
import pytest
from datetime import date
from core.database import DatabaseManager
from core.models import DepositDeduction, LeaseSettlement
from core.settlement_engine import (
    calculate_settlement,
    build_settlement_whatsapp_message,
    get_settlement_whatsapp_link,
    build_house_rules_whatsapp_message,
    get_house_rules_whatsapp_link,
    get_house_rules_template,
    save_house_rules_template,
    get_house_name,
    save_house_name,
    markdown_to_whatsapp,
    DEFAULT_HOUSE_RULES_TEMPLATE,
    STATUS_REFUND_TO_TENANT,
    STATUS_EXACT_BALANCE,
    STATUS_BALANCE_DUE_BY_TENANT,
    DEFAULT_DEDUCTION_CONCEPTS
)
from core.backup_manager import export_database_to_json, import_database_from_json


@pytest.fixture
def db_with_active_lease():
    db = DatabaseManager(":memory:")
    room = db.create_room("Cuarto 101 - Planta Baja", 3000.0)
    lease = db.start_lease(
        room_id=room.id,
        tenant_name="Mariana Gómez",
        tenant_phone="5215598765432",
        monthly_rent=3000.0,
        start_date="2026-06-01",
        deposit_amount=3000.0
    )
    return db, room, lease


def test_default_deduction_concepts_exist():
    assert len(DEFAULT_DEDUCTION_CONCEPTS) >= 4
    assert any("Pintura" in c for c in DEFAULT_DEDUCTION_CONCEPTS)
    assert any("Llaves" in c or "llaves" in c for c in DEFAULT_DEDUCTION_CONCEPTS)


def test_calculate_settlement_refund_positive():
    deductions = [
        DepositDeduction(concept="Pintura y resane", amount=450.0),
        DepositDeduction(concept="Reposición de llave", amount=150.0)
    ]
    summary = calculate_settlement(deposit_total=3000.0, deductions=deductions)
    assert summary["deposit_total"] == 3000.0
    assert summary["total_deductions"] == 600.0
    assert summary["refund_amount"] == 2400.0
    assert summary["status"] == STATUS_REFUND_TO_TENANT
    assert summary["balance_due_by_tenant"] == 0.0


def test_calculate_settlement_exact_balance():
    deductions = [
        DepositDeduction(concept="Daño en cancel de baño", amount=3000.0)
    ]
    summary = calculate_settlement(deposit_total=3000.0, deductions=deductions)
    assert summary["deposit_total"] == 3000.0
    assert summary["total_deductions"] == 3000.0
    assert summary["refund_amount"] == 0.0
    assert summary["status"] == STATUS_EXACT_BALANCE
    assert summary["balance_due_by_tenant"] == 0.0


def test_calculate_settlement_balance_due_by_tenant():
    deductions = [
        DepositDeduction(concept="Pintura completa", amount=2500.0),
        DepositDeduction(concept="Reparación eléctrica", amount=1200.0)
    ]
    summary = calculate_settlement(deposit_total=3000.0, deductions=deductions)
    assert summary["deposit_total"] == 3000.0
    assert summary["total_deductions"] == 3700.0
    assert summary["refund_amount"] == -700.0
    assert summary["status"] == STATUS_BALANCE_DUE_BY_TENANT
    assert summary["balance_due_by_tenant"] == 700.0


def test_calculate_settlement_empty_deductions():
    summary = calculate_settlement(deposit_total=2500.0, deductions=[])
    assert summary["deposit_total"] == 2500.0
    assert summary["total_deductions"] == 0.0
    assert summary["refund_amount"] == 2500.0
    assert summary["status"] == STATUS_REFUND_TO_TENANT


def test_build_settlement_whatsapp_message_formatting():
    deductions = [
        DepositDeduction(concept="Pintura y resane", amount=350.0),
        DepositDeduction(concept="Llave extraviada", amount=100.0)
    ]
    msg = build_settlement_whatsapp_message(
        tenant_name="Mariana Gómez",
        room_name="Cuarto 101",
        settlement_date=date(2026, 11, 24),
        deposit_total=3000.0,
        deductions=deductions,
        notes="Se revisó inventario y medidor."
    )
    assert "renTalo - Finiquito y Entrega de Habitación" in msg
    assert "Mariana Gómez" in msg
    assert "Cuarto 101" in msg
    assert "24 de noviembre de 2026" in msg
    assert "$3,000.00" in msg
    assert "Pintura y resane: -$350.00" in msg
    assert "Llave extraviada: -$100.00" in msg
    assert "*Total de deducciones:* -$450.00" in msg
    assert "*Saldo a favor a devolver al inquilino:* $2,550.00" in msg
    assert "Se revisó inventario y medidor." in msg


def test_build_settlement_whatsapp_message_no_deductions():
    msg = build_settlement_whatsapp_message(
        tenant_name="Mariana Gómez",
        room_name="Cuarto 101",
        settlement_date=date(2026, 11, 24),
        deposit_total=2800.0,
        deductions=[]
    )
    assert "excelentes condiciones" in msg.lower()
    assert "*Saldo a favor a devolver al inquilino:* $2,800.00" in msg


def test_get_settlement_whatsapp_link():
    deductions = [DepositDeduction(concept="Llave", amount=120.0)]
    msg = build_settlement_whatsapp_message(
        tenant_name="Mariana Gómez",
        room_name="Cuarto 101",
        settlement_date=date(2026, 11, 24),
        deposit_total=3000.0,
        deductions=deductions
    )
    link = get_settlement_whatsapp_link("5215598765432", msg)
    assert link.startswith("https://wa.me/5215598765432?text=")
    assert "Finiquito" in link or "renTalo" in link


def test_build_house_rules_whatsapp_message_and_link():
    msg = build_house_rules_whatsapp_message(tenant_name="Mariana Gómez", house_name="Casa Tulipanes")
    assert "Reglamento Interno" in msg
    assert "Mariana Gómez" in msg
    assert "Casa Tulipanes" in msg
    assert "10:00 PM a 07:00 AM" in msg
    assert "primeros 5 días" in msg

    link = get_house_rules_whatsapp_link("5215598765432", msg)
    assert link.startswith("https://wa.me/5215598765432?text=")
    assert "Reglamento" in link


def test_finalize_lease_with_settlement_in_db(db_with_active_lease):
    db, room, lease = db_with_active_lease
    deductions = [
        DepositDeduction(concept="Pintura de pared", amount=300.0),
        DepositDeduction(concept="Aseo general", amount=200.0)
    ]
    settlement = db.finalize_lease_with_settlement(
        lease_id=lease.id,
        settlement_date="2026-11-24",
        deposit_total=lease.deposit_amount,
        deductions=deductions,
        notes="Entrega sin contratiempos."
    )

    assert settlement.id is not None
    assert settlement.lease_id == lease.id
    assert settlement.deposit_total == 3000.0
    assert settlement.total_deductions == 500.0
    assert settlement.refund_amount == 2500.0
    assert len(settlement.deductions) == 2
    assert settlement.notes == "Entrega sin contratiempos."

    # Room must now be free
    updated_room = db.get_room(room.id)
    assert updated_room.is_occupied is False

    # Lease must now be inactive
    updated_lease = db.get_lease(lease.id)
    assert updated_lease.is_active is False
    assert updated_lease.end_date == "2026-11-24"

    # Query settlement back from DB
    fetched_settlement = db.get_settlement_for_lease(lease.id)
    assert fetched_settlement is not None
    assert fetched_settlement.id == settlement.id
    assert fetched_settlement.refund_amount == 2500.0
    assert len(fetched_settlement.deductions) == 2
    assert fetched_settlement.deductions[0].concept == "Pintura de pared"


def test_finalize_lease_invalid_id_raises(db_with_active_lease):
    db, _, _ = db_with_active_lease
    with pytest.raises(ValueError, match="no encontrado"):
        db.finalize_lease_with_settlement(
            lease_id=9999,
            settlement_date="2026-11-24",
            deposit_total=1000.0,
            deductions=[]
        )


def test_backup_json_roundtrip_preserves_settlements(db_with_active_lease, tmp_path):
    db, room, lease = db_with_active_lease
    deductions = [
        DepositDeduction(concept="Pintura", amount=400.0)
    ]
    db.finalize_lease_with_settlement(
        lease_id=lease.id,
        settlement_date="2026-11-24",
        deposit_total=lease.deposit_amount,
        deductions=deductions,
        notes="Respaldo con finiquito."
    )

    json_file = tmp_path / "backup_with_settlement.json"
    export_database_to_json(db, json_file)

    assert json_file.exists()
    with open(json_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert "settlements" in data
    assert len(data["settlements"]) == 1
    assert data["settlements"][0]["refund_amount"] == 2600.0

    # Restore into fresh DB
    new_db = DatabaseManager(":memory:")
    import_database_from_json(new_db, json_file)

    restored_settlements = new_db.get_all_settlements()
    assert len(restored_settlements) == 1
    s = restored_settlements[0]
    assert s.lease_id == lease.id
    assert s.refund_amount == 2600.0
    assert len(s.deductions) == 1
    assert s.deductions[0].concept == "Pintura"


def test_finalize_already_inactive_lease_raises(db_with_active_lease):
    db, _, lease = db_with_active_lease
    db.finalize_lease_with_settlement(
        lease_id=lease.id,
        settlement_date="2026-11-24",
        deposit_total=3000.0,
        deductions=[]
    )
    with pytest.raises(ValueError, match="ya fue finalizado"):
        db.finalize_lease_with_settlement(
            lease_id=lease.id,
            settlement_date="2026-11-25",
            deposit_total=3000.0,
            deductions=[]
        )


def test_merge_database_from_json_preserves_settlements_without_duplicates(tmp_path):
    from core.backup_manager import merge_database_from_json

    db_sup1 = DatabaseManager(":memory:")
    r1 = db_sup1.create_room("Cuarto A", 2500.0)
    l1 = db_sup1.start_lease(r1.id, "Carlos", "5215511112222", 2500.0, "2026-01-01", deposit_amount=2500.0)
    db_sup1.finalize_lease_with_settlement(
        lease_id=l1.id,
        settlement_date="2026-11-20",
        deposit_total=2500.0,
        deductions=[DepositDeduction(concept="Llaves", amount=150.0)],
        notes="Finiquito supervisor 1"
    )
    sup1_json = tmp_path / "sup1.json"
    export_database_to_json(db_sup1, sup1_json)

    db_sup2 = DatabaseManager(":memory:")
    db_sup2.create_room("Cuarto B", 3000.0)

    stats1 = merge_database_from_json(db_sup2, sup1_json)
    assert stats1["settlements_merged"] == 1
    assert len(db_sup2.get_all_settlements()) == 1

    # Re-merging the same file must not duplicate the settlement
    stats2 = merge_database_from_json(db_sup2, sup1_json)
    assert stats2["settlements_merged"] == 0
    assert len(db_sup2.get_all_settlements()) == 1


def test_custom_house_rules_persistence_and_markdown_conversion():
    db = DatabaseManager(":memory:")
    # Default values before customization
    assert get_house_name(db) == "renTalo"
    assert get_house_rules_template(db) == DEFAULT_HOUSE_RULES_TEMPLATE

    # Save custom property name and Markdown/WhatsApp hybrid rules with literal braces
    save_house_name(db, "Casa Girasoles")
    custom_rules = (
        "## Reglamento de {house_name}\n"
        "Hola **{tenant_name}** ({zona}):\n"
        "- No fumar\n"
        "- _Silencio_ después de las 10 PM"
    )
    save_house_rules_template(db, custom_rules)

    assert get_house_name(db) == "Casa Girasoles"
    msg = build_house_rules_whatsapp_message(tenant_name="Sofía", db=db)

    assert "*Reglamento de Casa Girasoles*" in msg
    assert "Hola *Sofía* ({zona}):" in msg
    assert "• No fumar" in msg
    assert "• _Silencio_ después de las 10 PM" in msg
    assert "## " not in msg
    assert "**" not in msg

    # Preserves native WhatsApp formatting untouched
    native_wa = "*Título* y _cursiva_ y ~tachado~"
    assert markdown_to_whatsapp(native_wa) == native_wa
