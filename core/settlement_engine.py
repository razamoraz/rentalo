from datetime import date
from typing import List, Dict, Any, Optional
from core.models import DepositDeduction, LeaseSettlement
from core.billing_engine import get_spanish_month_name, generate_whatsapp_link

DEFAULT_DEDUCTION_CONCEPTS: List[str] = [
    "Pintura y resane de muros",
    "Reposición de llaves de acceso",
    "Limpieza profunda de habitación",
    "Reparación de desperfectos o daños",
    "Adeudo de servicios o días adicionales"
]

STATUS_REFUND_TO_TENANT = "REFUND_TO_TENANT"
STATUS_EXACT_BALANCE = "EXACT_BALANCE"
STATUS_BALANCE_DUE_BY_TENANT = "BALANCE_DUE_BY_TENANT"


def calculate_settlement(
    deposit_total: float,
    deductions: List[DepositDeduction]
) -> Dict[str, Any]:
    """
    Calcula la liquidación financiera del depósito en garantía contra las deducciones:
    - total_deductions: suma de deducciones legítimas (montos no negativos).
    - refund_amount: deposit_total - total_deductions.
    - status:
        * REFUND_TO_TENANT: saldo positivo a devolver al inquilino.
        * EXACT_BALANCE: cuentas exactamente saldadas ($0.00).
        * BALANCE_DUE_BY_TENANT: saldo negativo, el inquilino adeuda la diferencia.
    """
    deposit_clean = max(0.0, float(deposit_total))
    total_deductions = round(sum(max(0.0, float(d.amount)) for d in deductions), 2)
    refund_amount = round(deposit_clean - total_deductions, 2)

    if refund_amount > 0:
        status = STATUS_REFUND_TO_TENANT
    elif refund_amount == 0:
        status = STATUS_EXACT_BALANCE
    else:
        status = STATUS_BALANCE_DUE_BY_TENANT

    return {
        "deposit_total": deposit_clean,
        "total_deductions": total_deductions,
        "refund_amount": refund_amount,
        "status": status,
        "balance_due_by_tenant": abs(refund_amount) if refund_amount < 0 else 0.0
    }


def build_settlement_whatsapp_message(
    tenant_name: str,
    room_name: str,
    settlement_date: date,
    deposit_total: float,
    deductions: List[DepositDeduction],
    notes: Optional[str] = None
) -> str:
    """
    Genera el comprobante formal y cordial de finiquito y entrega-recepción para enviar por WhatsApp.
    """
    summary = calculate_settlement(deposit_total, deductions)
    month_name = get_spanish_month_name(settlement_date.month)
    fecha_str = f"{settlement_date.day} de {month_name} de {settlement_date.year}"

    lines = [
        "🧾 *renTalo - Finiquito y Entrega de Habitación*",
        "",
        f"Hola *{tenant_name}*, le compartimos el resumen formal de entrega-recepción para la habitación *{room_name}* al día {fecha_str}:",
        "",
        f"💰 *Depósito en garantía:* ${summary['deposit_total']:,.2f}"
    ]

    # Deducciones
    if deductions and summary["total_deductions"] > 0:
        lines.append("")
        lines.append("📋 *Deducciones aplicadas:*")
        for d in deductions:
            if d.amount > 0:
                lines.append(f"  • {d.concept}: -${d.amount:,.2f}")
        lines.append(f"*Total de deducciones:* -${summary['total_deductions']:,.2f}")
    else:
        lines.append("")
        lines.append("📋 *Deducciones aplicadas:* Ninguna. Habitación entregada en excelentes condiciones.")

    # Saldo final
    lines.append("")
    if summary["status"] == STATUS_REFUND_TO_TENANT:
        lines.append(f"✅ *Saldo a favor a devolver al inquilino:* ${summary['refund_amount']:,.2f}")
    elif summary["status"] == STATUS_EXACT_BALANCE:
        lines.append("✅ *Cuentas saldadas ($0.00).* No quedan adeudos ni saldos pendientes.")
    else:
        lines.append(f"⚠️ *Saldo pendiente a liquidar por el inquilino:* ${summary['balance_due_by_tenant']:,.2f}")

    if notes and notes.strip():
        lines.append("")
        lines.append(f"📝 *Observaciones:* {notes.strip()}")

    lines.append("")
    lines.append("Agradecemos su estancia y confianza con nosotros. ¡Le deseamos el mayor de los éxitos!")

    return "\n".join(lines)


def get_settlement_whatsapp_link(
    tenant_phone: str,
    message: str
) -> str:
    """Genera el enlace de WhatsApp codificado con el finiquito de entrega."""
    return generate_whatsapp_link(tenant_phone, message)


def build_house_rules_whatsapp_message(
    tenant_name: Optional[str] = None,
    house_name: str = "renTalo"
) -> str:
    """
    Genera el mensaje cordial con el Reglamento Interno y Normas de Convivencia para nuevos inquilinos.
    """
    saludo = f"Hola *{tenant_name}*," if tenant_name else "Hola,"
    lines = [
        "📜 *renTalo - Reglamento Interno y Normas de Convivencia*",
        "",
        f"{saludo} le damos la más cordial bienvenida a *{house_name}*.",
        "Para garantizar la tranquilidad, seguridad y comodidad de todos, le compartimos nuestras normas básicas de convivencia:",
        "",
        "1. ⏰ *Puntualidad en Rentas:* El pago se realiza dentro de los primeros 5 días naturales de cada mes.",
        "2. 🔇 *Horario de Silencio:* De 10:00 PM a 07:00 AM se solicita mantener el volumen moderado (música, TV, llamadas).",
        "3. 🧹 *Áreas Comunes:* Mantener limpias y ordenadas las áreas compartidas (baño, cocina, pasillos) después de usarlas.",
        "4. 🔑 *Seguridad y Llaves:* Mantener la puerta principal con llave al entrar y salir. Prohibido duplicar llaves sin autorización.",
        "5. 👥 *Visitas:* Las visitas deben respetar el reglamento y no permanecer en horarios nocturnos de descanso sin aviso previo.",
        "6. 🚭 *Cuidado de las Instalaciones:* Prohibido fumar dentro de las habitaciones y cuidar el mobiliario e instalaciones de la casa.",
        "",
        "¡Agradecemos mucho su colaboración para mantener un ambiente agradable y respetuoso para todos!"
    ]
    return "\n".join(lines)


def get_house_rules_whatsapp_link(
    tenant_phone: str,
    message: str
) -> str:
    """Genera el enlace de WhatsApp con el reglamento de convivencia."""
    return generate_whatsapp_link(tenant_phone, message)
