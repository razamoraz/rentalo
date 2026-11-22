import calendar
import re
import urllib.parse
from datetime import date
from typing import List, Optional
from core.models import Lease, Payment

STATUS_PAGADO = "PAGADO"
STATUS_PENDIENTE = "PENDIENTE"
STATUS_ATRASADO = "ATRASADO"

MESES_ES = {
    1: "enero",
    2: "febrero",
    3: "marzo",
    4: "abril",
    5: "mayo",
    6: "junio",
    7: "julio",
    8: "agosto",
    9: "septiembre",
    10: "octubre",
    11: "noviembre",
    12: "diciembre"
}


def get_spanish_month_name(month: int) -> str:
    if 1 <= month <= 12:
        return MESES_ES[month]
    raise ValueError(f"Mes inválido: {month}. Debe ser entre 1 y 12.")


def calculate_proportional_rent(monthly_rent: float, start_date: date) -> float:
    """
    Calcula el cobro proporcional del primer mes según la fecha de inicio:
    - Si el contrato inicia dentro de los primeros 5 días naturales (1 al 5),
      se cobra el mes completo normal.
    - Si inicia a partir del día 6, calcula el cobro proporcional exacto
      de los días restantes del mes.
    """
    if start_date.day <= 5:
        return float(monthly_rent)

    total_days = calendar.monthrange(start_date.year, start_date.month)[1]
    remaining_days = total_days - start_date.day + 1
    daily_rate = monthly_rent / total_days
    return round(daily_rate * remaining_days, 2)


def get_payment_status(lease: Lease, payments: List[Payment], reference_date: date) -> str:
    """
    Determina el estado del pago de renta del mes actual (según reference_date):
    - PAGADO: si existe un pago para el año y mes de reference_date.
    - PENDIENTE: si no hay pago pero estamos dentro de la ventana de los primeros 5 días naturales (1 al 5).
    - ATRASADO: si no hay pago y han transcurrido más de 5 días naturales (día 6 en adelante).
    """
    for p in payments:
        if p.lease_id == lease.id and p.billing_year == reference_date.year and p.billing_month == reference_date.month:
            return STATUS_PAGADO

    if 1 <= reference_date.day <= 5:
        return STATUS_PENDIENTE

    return STATUS_ATRASADO


def clean_phone_number(phone: str) -> str:
    """Elimina caracteres no numéricos dejando solo dígitos."""
    return re.sub(r"\D", "", phone)


def generate_whatsapp_link(phone: str, message: str) -> str:
    """Genera un link de WhatsApp con el mensaje codificado en URL."""
    digits = clean_phone_number(phone)
    encoded = urllib.parse.quote(message)
    return f"https://wa.me/{digits}?text={encoded}"


def build_welcome_lease_message(
    tenant_name: str,
    room_name: str,
    start_date: str,
    monthly_rent: float,
    deposit_amount: float,
    first_month_rent: float
) -> str:
    """
    Genera el mensaje de bienvenida y desglose inicial de entrega de habitación en WhatsApp:
    - Fecha de inicio.
    - Depósito en garantía.
    - Renta inicial (completa o cobro proporcional por días restantes).
    - Renta mensual regular futura.
    """
    total_inicial = deposit_amount + first_month_rent
    mensaje = (
        f"¡Hola {tenant_name}! Le damos la cordial bienvenida a {room_name}.\n\n"
        f"Le compartimos el resumen de su inicio de contrato:\n"
        f"📅 Fecha de inicio: {start_date}\n"
        f"🔒 Depósito en garantía: ${deposit_amount:,.2f}\n"
        f"💵 Primer pago (cobro proporcional por días restantes): ${first_month_rent:,.2f}\n"
        f"💰 Total inicial acordado: ${total_inicial:,.2f}\n\n"
        f"A partir del siguiente mes, su renta regular será de ${monthly_rent:,.2f} "
        f"a cubrirse dentro de los primeros 5 días naturales de cada mes. ¡Muchas gracias!"
    )
    return mensaje


def build_payment_reminder_message(
    tenant_name: str,
    room_name: str,
    year: int,
    month: int,
    amount: float,
    status: str
) -> str:
    """
    Genera una plantilla de mensaje en español natural según el estado:
    - PENDIENTE: recordatorio amigable indicando la renta del mes y monto.
    - ATRASADO: recordatorio atento notificando que han pasado los primeros 5 días.
    - PAGADO: comprobante o confirmación de recepción.
    """
    month_name = get_spanish_month_name(month)
    formatted_amount = f"${amount:,.2f}"

    if status == STATUS_PENDIENTE:
        return (
            f"Hola {tenant_name}, le recordamos cordialmente que la renta de {room_name} "
            f"correspondiente a {month_name} de {year} por un monto de {formatted_amount} "
            f"está lista para ser cubierta dentro de la ventana de los primeros 5 días. ¡Muchas gracias!"
        )
    elif status == STATUS_ATRASADO:
        return (
            f"Hola {tenant_name}, le recordamos de manera atenta que han pasado los primeros 5 días "
            f"del mes para el pago de la renta de {room_name} correspondiente a {month_name} de {year} "
            f"por {formatted_amount}. Le solicitamos comunicarse para coordinar su pago. Gracias."
        )
    elif status == STATUS_PAGADO:
        return (
            f"Hola {tenant_name}, le confirmamos que el pago de la renta de {room_name} "
            f"correspondiente a {month_name} de {year} por {formatted_amount} ha sido recibido con éxito. "
            f"¡Muchas gracias por su puntualidad!"
        )
    else:
        return f"Hola {tenant_name}, detalle de renta de {room_name}: {formatted_amount} para {month_name} de {year}."


def get_whatsapp_payment_link(
    lease: Lease,
    room_name: str,
    reference_date: date,
    amount: float,
    status: str
) -> str:
    """Genera el enlace directo a WhatsApp para el inquilino."""
    msg = build_payment_reminder_message(
        tenant_name=lease.tenant_name,
        room_name=room_name,
        year=reference_date.year,
        month=reference_date.month,
        amount=amount,
        status=status
    )
    return generate_whatsapp_link(lease.tenant_phone, msg)
