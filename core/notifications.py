from datetime import date
from typing import Optional, Dict, Any
from core.database import DatabaseManager
from core.billing_engine import (
    get_payment_status,
    get_spanish_month_name,
    STATUS_PAGADO,
    STATUS_PENDIENTE,
    STATUS_ATRASADO
)

TYPE_PENDIENTE = "PENDIENTE"
TYPE_ATRASADO = "ATRASADO"


def get_monthly_reminder_status(
    db: DatabaseManager,
    reference_date: date
) -> Optional[Dict[str, Any]]:
    """
    Evalúa si se debe emitir una notificación local mensual según el día del mes:
    - Días 1 al 5: Recordatorio cordial de inicio de cobro si hay cuartos pendientes.
    - Día 6 en adelante: Aviso de atención si hay cuartos atrasados pasados los 5 días de gracia.
    Verifica en settings que no se haya notificado previamente en el mismo mes para el mismo tipo.
    """
    active_leases = db.get_all_leases(active_only=True)
    if not active_leases:
        return None

    all_payments = db.get_all_payments()
    pending_count = 0
    overdue_count = 0

    for lease in active_leases:
        lease_payments = [p for p in all_payments if p.lease_id == lease.id]
        status = get_payment_status(lease, lease_payments, reference_date)
        if status == STATUS_PENDIENTE:
            pending_count += 1
        elif status == STATUS_ATRASADO:
            overdue_count += 1

    year = reference_date.year
    month = reference_date.month
    month_name = get_spanish_month_name(month)

    # 1. Ventana de los primeros 5 días naturales (1 al 5)
    if 1 <= reference_date.day <= 5 and pending_count > 0:
        setting_key = f"notif_{year}_{month}_{TYPE_PENDIENTE}"
        if db.get_setting(setting_key) is None:
            return {
                "title": "RentaFácil - Cobro de Renta",
                "message": (
                    f"Inicia el período de cobro de {month_name}. "
                    f"Tienes {pending_count} cuarto(s) pendiente(s) de cobro."
                ),
                "type": TYPE_PENDIENTE,
                "count": pending_count
            }

    # 2. Pasados los 5 días naturales (día 6 en adelante)
    elif reference_date.day >= 6 and overdue_count > 0:
        setting_key = f"notif_{year}_{month}_{TYPE_ATRASADO}"
        if db.get_setting(setting_key) is None:
            return {
                "title": "RentaFácil - Rentas Atrasadas",
                "message": (
                    f"Atención: Han transcurrido los primeros 5 días de {month_name}. "
                    f"Tienes {overdue_count} cuarto(s) con renta atrasada."
                ),
                "type": TYPE_ATRASADO,
                "count": overdue_count
            }

    return None


def mark_notification_sent(
    db: DatabaseManager,
    reference_date: date,
    notification_type: str
) -> None:
    """Marca en la base de datos que ya se envió la notificación mensual de este tipo."""
    setting_key = f"notif_{reference_date.year}_{reference_date.month}_{notification_type}"
    db.set_setting(setting_key, date.today().isoformat())

