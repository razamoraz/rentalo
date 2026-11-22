import csv
import json
from datetime import date, datetime
from pathlib import Path
from typing import Optional, Union, Dict, Any

from core.database import DatabaseManager
from core.models import Room, Lease, Payment
from core.billing_engine import (
    get_payment_status,
    generate_whatsapp_link,
    get_spanish_month_name
)


def export_payments_csv(db: DatabaseManager, target_path: Union[str, Path]) -> Path:
    """
    Exporta el historial de pagos a un archivo CSV con codificación UTF-8 con BOM (utf-8-sig)
    para que Excel y Google Sheets lo abran sin problemas de caracteres o acentos en español.
    """
    path = Path(target_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    payments = db.get_all_payments()
    leases_map: Dict[int, Lease] = {l.id: l for l in db.get_all_leases(active_only=False) if l.id is not None}
    rooms_map: Dict[int, Room] = {r.id: r for r in db.get_all_rooms() if r.id is not None}

    headers = ["ID Pago", "Cuarto", "Inquilino", "Año", "Mes", "Monto", "Método", "Comprobante", "Fecha de Pago"]

    with open(path, mode="w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(headers)

        for p in payments:
            lease = leases_map.get(p.lease_id)
            tenant_name = lease.tenant_name if lease else "Desconocido"
            room_name = rooms_map.get(lease.room_id).name if (lease and lease.room_id in rooms_map) else "Desconocido"
            proof_display = p.proof_image_path if p.proof_image_path else "Sin comprobante"
            method_display = p.payment_method if p.payment_method else "TRANSFERENCIA"
            writer.writerow([
                p.id,
                room_name,
                tenant_name,
                p.billing_year,
                get_spanish_month_name(p.billing_month).capitalize(),
                f"{p.amount:.2f}",
                method_display,
                proof_display,
                p.paid_date
            ])

    return path


def export_rooms_status_csv(
    db: DatabaseManager,
    target_path: Union[str, Path],
    reference_date: Optional[date] = None
) -> Path:
    """
    Exporta el estado actual de los cuartos, depósito y su estatus de pago para el mes de referencia a CSV.
    """
    path = Path(target_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    if reference_date is None:
        reference_date = date.today()

    rooms = db.get_all_rooms()
    headers = ["ID Cuarto", "Cuarto", "Renta Base", "Estado", "Inquilino", "Teléfono", "Depósito", "Estatus Renta"]

    with open(path, mode="w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(headers)

        for room in rooms:
            if room.is_occupied:
                active_lease = db.get_active_lease_for_room(room.id)
                if active_lease:
                    payments = db.get_payments_for_lease(active_lease.id)
                    rent_status = get_payment_status(active_lease, payments, reference_date)
                    writer.writerow([
                        room.id,
                        room.name,
                        f"{room.default_rent:.2f}",
                        "Ocupado",
                        active_lease.tenant_name,
                        active_lease.tenant_phone,
                        f"{active_lease.deposit_amount:.2f}",
                        rent_status
                    ])
                    continue

                writer.writerow([
                    room.id,
                    room.name,
                    f"{room.default_rent:.2f}",
                    "Ocupado",
                    "-",
                    "-",
                    "0.00",
                    "-"
                ])
            else:
                writer.writerow([
                    room.id,
                    room.name,
                    f"{room.default_rent:.2f}",
                    "Disponible",
                    "-",
                    "-",
                    "0.00",
                    "-"
                ])

    return path


def export_database_to_json(db: DatabaseManager, target_path: Union[str, Path]) -> Path:
    """
    Exporta el estado completo de la base de datos (cuartos, contratos, pagos y configuraciones)
    en formato JSON portátil.
    """
    path = Path(target_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    rooms = [r.to_dict() for r in db.get_all_rooms()]
    leases = [l.to_dict() for l in db.get_all_leases(active_only=False)]
    payments = [p.to_dict() for p in db.get_all_payments()]
    settings = db.get_all_settings()

    payload = {
        "version": 1,
        "app": "renTalo",
        "exported_at": datetime.now().isoformat(),
        "rooms": rooms,
        "leases": leases,
        "payments": payments,
        "settings": settings
    }

    with open(path, mode="w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    return path


def import_database_from_json(
    db: DatabaseManager,
    source_path: Union[str, Path],
    clear_existing: bool = True
) -> bool:
    """
    Restaura el estado completo de la base de datos desde un archivo JSON dentro de una transacción.
    Si ocurre cualquier error o los datos son inválidos, realiza un rollback completo.
    """
    path = Path(source_path)
    with open(path, mode="r", encoding="utf-8") as f:
        data: Dict[str, Any] = json.load(f)

    if not isinstance(data, dict) or "rooms" not in data or "leases" not in data or "payments" not in data:
        raise ValueError("El archivo JSON no tiene la estructura requerida de renTalo.")

    # Validar formato básico de elementos
    for r in data["rooms"]:
        if "name" not in r or "default_rent" not in r:
            raise ValueError("Datos de cuartos inválidos en el archivo JSON.")

    for l in data["leases"]:
        if "room_id" not in l or "tenant_name" not in l or "tenant_phone" not in l:
            raise ValueError("Datos de contratos inválidos en el archivo JSON.")

    for p in data["payments"]:
        if "lease_id" not in p or "billing_year" not in p or "billing_month" not in p:
            raise ValueError("Datos de pagos inválidos en el archivo JSON.")

    # Ejecutar dentro de una transacción segura
    with db.conn:
        if clear_existing:
            db.conn.execute("DELETE FROM payments")
            db.conn.execute("DELETE FROM leases")
            db.conn.execute("DELETE FROM rooms")
            db.conn.execute("DELETE FROM settings")

        for r in data["rooms"]:
            db.conn.execute(
                "INSERT INTO rooms (id, name, default_rent, is_occupied) VALUES (?, ?, ?, ?)",
                (r.get("id"), r["name"], float(r["default_rent"]), 1 if r.get("is_occupied") else 0)
            )

        for l in data["leases"]:
            db.conn.execute(
                """
                INSERT INTO leases (id, room_id, tenant_name, tenant_phone, monthly_rent, start_date, end_date, is_active, deposit_amount, initial_rent)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    l.get("id"),
                    int(l["room_id"]),
                    l["tenant_name"],
                    l["tenant_phone"],
                    float(l["monthly_rent"]),
                    l["start_date"],
                    l.get("end_date"),
                    1 if l.get("is_active", True) else 0,
                    float(l.get("deposit_amount", 0.0)),
                    float(l["initial_rent"]) if l.get("initial_rent") is not None else None
                )
            )

        for p in data["payments"]:
            db.conn.execute(
                """
                INSERT INTO payments (id, lease_id, billing_year, billing_month, amount, paid_date, proof_image_path, payment_method)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    p.get("id"),
                    int(p["lease_id"]),
                    int(p["billing_year"]),
                    int(p["billing_month"]),
                    float(p["amount"]),
                    p["paid_date"],
                    p.get("proof_image_path"),
                    p.get("payment_method", "TRANSFERENCIA")
                )
            )

        settings = data.get("settings", {})
        if isinstance(settings, dict):
            for k, v in settings.items():
                db.conn.execute(
                    "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (k, str(v))
                )

    return True


def merge_database_from_json(
    db: DatabaseManager,
    source_path: Union[str, Path]
) -> Dict[str, Any]:
    """
    Combina e integra datos de otro supervisor desde un archivo JSON sin borrar datos existentes (Merge seguro).
    - Asocia cuartos por nombre o crea los que no existan.
    - Asocia contratos por cuarto, inquilino y fecha de inicio.
    - Inserta o actualiza pagos mediante la restricción de unicidad (lease_id, billing_year, billing_month).
    - Preserva configuraciones sin sobreescritura destructiva.
    """
    path = Path(source_path)
    with open(path, mode="r", encoding="utf-8") as f:
        data: Dict[str, Any] = json.load(f)

    if not isinstance(data, dict) or "rooms" not in data or "leases" not in data or "payments" not in data:
        raise ValueError("El archivo JSON no tiene la estructura requerida de renTalo.")

    rooms_count = 0
    leases_count = 0
    payments_count = 0

    with db.conn:
        # 1. Procesar Cuartos
        existing_rooms = {r.name.strip().lower(): r for r in db.get_all_rooms()}
        room_id_map: Dict[int, int] = {}

        for r in data["rooms"]:
            old_id = r.get("id")
            name_key = r["name"].strip().lower()

            if name_key in existing_rooms:
                dest_room = existing_rooms[name_key]
                if old_id is not None and dest_room.id is not None:
                    room_id_map[old_id] = dest_room.id
                if r.get("is_occupied") and not dest_room.is_occupied:
                    db.conn.execute("UPDATE rooms SET is_occupied = 1 WHERE id = ?", (dest_room.id,))
            else:
                cursor = db.conn.execute(
                    "INSERT INTO rooms (name, default_rent, is_occupied) VALUES (?, ?, ?)",
                    (r["name"], float(r["default_rent"]), 1 if r.get("is_occupied") else 0)
                )
                new_room_id = cursor.lastrowid
                if old_id is not None and new_room_id is not None:
                    room_id_map[old_id] = new_room_id
                existing_rooms[name_key] = Room(
                    id=new_room_id,
                    name=r["name"],
                    default_rent=float(r["default_rent"]),
                    is_occupied=bool(r.get("is_occupied"))
                )
                rooms_count += 1

        # 2. Procesar Contratos
        existing_leases = db.get_all_leases(active_only=False)
        lease_lookup = {
            (l.room_id, l.tenant_name.strip().lower(), l.start_date): l
            for l in existing_leases
        }
        lease_id_map: Dict[int, int] = {}

        for l in data["leases"]:
            old_lease_id = l.get("id")
            old_room_id = int(l["room_id"])
            dest_room_id = room_id_map.get(old_room_id)

            if dest_room_id is None:
                continue

            lease_key = (dest_room_id, l["tenant_name"].strip().lower(), l["start_date"])

            if lease_key in lease_lookup:
                dest_lease = lease_lookup[lease_key]
                if old_lease_id is not None and dest_lease.id is not None:
                    lease_id_map[old_lease_id] = dest_lease.id
                db.conn.execute(
                    """
                    UPDATE leases
                    SET tenant_phone = ?, monthly_rent = ?, deposit_amount = ?, is_active = ?, end_date = ?
                    WHERE id = ?
                    """,
                    (
                        l["tenant_phone"],
                        float(l["monthly_rent"]),
                        float(l.get("deposit_amount", dest_lease.deposit_amount)),
                        1 if l.get("is_active", True) else 0,
                        l.get("end_date"),
                        dest_lease.id
                    )
                )
            else:
                cursor = db.conn.execute(
                    """
                    INSERT INTO leases (room_id, tenant_name, tenant_phone, monthly_rent, start_date, end_date, is_active, deposit_amount, initial_rent)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        dest_room_id,
                        l["tenant_name"],
                        l["tenant_phone"],
                        float(l["monthly_rent"]),
                        l["start_date"],
                        l.get("end_date"),
                        1 if l.get("is_active", True) else 0,
                        float(l.get("deposit_amount", 0.0)),
                        float(l["initial_rent"]) if l.get("initial_rent") is not None else None
                    )
                )
                new_lease_id = cursor.lastrowid
                if old_lease_id is not None and new_lease_id is not None:
                    lease_id_map[old_lease_id] = new_lease_id
                leases_count += 1

        # 3. Procesar Pagos
        for p in data["payments"]:
            old_lease_id = int(p["lease_id"])
            dest_lease_id = lease_id_map.get(old_lease_id)

            if dest_lease_id is None:
                continue

            db.conn.execute(
                """
                INSERT INTO payments (lease_id, billing_year, billing_month, amount, paid_date, proof_image_path, payment_method)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(lease_id, billing_year, billing_month)
                DO UPDATE SET
                    amount = excluded.amount,
                    paid_date = excluded.paid_date,
                    proof_image_path = COALESCE(excluded.proof_image_path, payments.proof_image_path),
                    payment_method = excluded.payment_method
                """,
                (
                    dest_lease_id,
                    int(p["billing_year"]),
                    int(p["billing_month"]),
                    float(p["amount"]),
                    p["paid_date"],
                    p.get("proof_image_path"),
                    p.get("payment_method", "TRANSFERENCIA")
                )
            )
            payments_count += 1

        # 4. Sincronizar ocupación de cuartos con los contratos activos resultantes
        active_room_ids = {l.room_id for l in db.get_all_leases(active_only=True)}
        for room in db.get_all_rooms():
            is_occ = 1 if room.id in active_room_ids else 0
            if (1 if room.is_occupied else 0) != is_occ:
                db.conn.execute("UPDATE rooms SET is_occupied = ? WHERE id = ?", (is_occ, room.id))

    return {
        "success": True,
        "rooms_merged": rooms_count,
        "leases_merged": leases_count,
        "payments_merged": payments_count
    }


def get_last_backup_date(db: DatabaseManager) -> Optional[str]:
    """Obtiene la fecha del último respaldo registrado (formato ISO YYYY-MM-DD)."""
    return db.get_setting("last_backup_date")


def record_backup_completed(db: DatabaseManager, backup_date: Optional[date] = None) -> None:
    """Registra en la configuración que se ha realizado un respaldo exitoso."""
    if backup_date is None:
        backup_date = date.today()
    db.set_setting("last_backup_date", backup_date.isoformat())


def is_backup_overdue(db: DatabaseManager, reference_date: Optional[date] = None, days: int = 180) -> bool:
    """
    Retorna True si nunca se ha realizado un respaldo o si han transcurrido >= days (por defecto 180 días / 6 meses).
    """
    if reference_date is None:
        reference_date = date.today()

    last_date_str = get_last_backup_date(db)
    if not last_date_str:
        return True

    try:
        last_date = date.fromisoformat(last_date_str)
        return (reference_date - last_date).days >= days
    except ValueError:
        return True


def build_backup_reminder_whatsapp_message(
    operator_name: Optional[str] = None,
    days_since_last: Optional[int] = None
) -> str:
    """
    Genera un mensaje cordial en español para recordar al operador realizar el respaldo de seguridad.
    """
    saludo = f"Estimado(a) {operator_name}" if operator_name else "Aviso de renTalo"
    tiempo_texto = f"hace más de {days_since_last} días" if days_since_last else "hace más de 6 meses"

    return (
        f"{saludo}: Se ha detectado que su último respaldo de seguridad se realizó {tiempo_texto}. "
        f"Por favor genere un respaldo en CSV o JSON desde el menú de la aplicación para proteger la información de sus rentas."
    )


def get_operator_backup_whatsapp_link(
    operator_phone: str,
    message: str
) -> str:
    """Genera el enlace de WhatsApp con el recordatorio de respaldo para el operador."""
    return generate_whatsapp_link(operator_phone, message)
