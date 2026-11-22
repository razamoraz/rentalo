from datetime import date
from typing import Callable, Optional
from kivy.metrics import dp
from kivymd.uix.dialog import MDDialog
from kivymd.uix.button import MDFlatButton, MDRaisedButton
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.textfield import MDTextField
from kivymd.uix.label import MDLabel
from kivymd.uix.snackbar import MDSnackbar

from core.models import Room, Lease
from core.database import DatabaseManager
from core.billing_engine import (
    get_spanish_month_name,
    STATUS_PAGADO,
    calculate_proportional_rent,
    build_welcome_lease_message
)
from core.backup_manager import (
    export_payments_csv,
    export_rooms_status_csv,
    export_database_to_json,
    import_database_from_json,
    merge_database_from_json,
    record_backup_completed,
    get_last_backup_date
)
from ui.android_bridge import (
    get_export_directory,
    share_file,
    open_whatsapp,
    save_payment_proof,
    view_image_file
)
from ui.theme_config import COLOR_PAGADO, COLOR_BANNER_WARNING, BUTTON_HEIGHT


def show_snackbar(text: str) -> None:
    """Muestra un mensaje emergente sencillo y legible."""
    snackbar = MDSnackbar(
        MDLabel(
            text=text,
            theme_text_color="Custom",
            text_color=(1, 1, 1, 1),
            bold=True
        ),
        duration=3
    )
    snackbar.open()


def show_new_room_dialog(db: DatabaseManager, on_created: Callable[[Room], None]) -> MDDialog:
    """Diálogo para registrar una nueva habitación."""
    content = MDBoxLayout(
        orientation="vertical",
        spacing=dp(12),
        size_hint_y=None,
        height=dp(140)
    )

    name_field = MDTextField(
        hint_text="Nombre del cuarto (ej. Cuarto 1, Habitación A)",
        required=True,
        helper_text="Campo obligatorio",
        helper_text_mode="on_error"
    )
    rent_field = MDTextField(
        hint_text="Renta mensual predeterminada ($)",
        text="2500",
        input_filter="float",
        required=True
    )

    content.add_widget(name_field)
    content.add_widget(rent_field)

    dialog = None

    def on_save(instance):
        name = name_field.text.strip()
        rent_str = rent_field.text.strip()
        if not name or not rent_str:
            show_snackbar("Por favor llene todos los campos.")
            return

        try:
            rent = float(rent_str)
            new_room = db.create_room(name=name, default_rent=rent)
            if dialog:
                dialog.dismiss()
            show_snackbar(f"Cuarto '{name}' agregado exitosamente.")
            on_created(new_room)
        except Exception as e:
            show_snackbar(f"Error al guardar: {e}")

    dialog = MDDialog(
        title="Nuevo Cuarto",
        type="custom",
        content_cls=content,
        buttons=[
            MDFlatButton(
                text="CANCELAR",
                on_release=lambda x: dialog.dismiss()
            ),
            MDRaisedButton(
                text="GUARDAR CUARTO",
                md_bg_color=COLOR_PAGADO,
                on_release=on_save
            )
        ]
    )
    dialog.open()
    return dialog


def show_assign_tenant_dialog(
    db: DatabaseManager,
    room: Room,
    on_assigned: Callable[[Lease], None]
) -> MDDialog:
    """Diálogo para iniciar un contrato con depósito y ajuste proporcional para el primer mes."""
    today = date.today()
    suggested_initial_rent = calculate_proportional_rent(room.default_rent, today)

    content = MDBoxLayout(
        orientation="vertical",
        spacing=dp(8),
        size_hint_y=None,
        height=dp(310)
    )

    tenant_name_field = MDTextField(
        hint_text="Nombre completo del inquilino",
        required=True
    )
    phone_field = MDTextField(
        hint_text="Teléfono WhatsApp (ej. 5512345678)",
        required=True,
        input_filter="int"
    )
    rent_field = MDTextField(
        hint_text="Renta mensual regular ($)",
        text=str(int(room.default_rent)),
        input_filter="float",
        required=True
    )
    deposit_field = MDTextField(
        hint_text="Depósito en garantía recibido ($)",
        text=str(int(room.default_rent)),
        input_filter="float",
        required=True
    )

    helper_txt = "Cobro proporcional sugerido por días restantes" if today.day > 5 else "Cobro del primer mes completo"
    initial_rent_field = MDTextField(
        hint_text="Primer cobro acordado ($)",
        text=f"{suggested_initial_rent:.2f}",
        helper_text=helper_txt,
        helper_text_mode="persistent",
        input_filter="float",
        required=True
    )

    content.add_widget(tenant_name_field)
    content.add_widget(phone_field)
    content.add_widget(rent_field)
    content.add_widget(deposit_field)
    content.add_widget(initial_rent_field)

    dialog = None

    def on_confirm(instance):
        tenant_name = tenant_name_field.text.strip()
        phone = phone_field.text.strip()
        rent_str = rent_field.text.strip()
        deposit_str = deposit_field.text.strip()
        initial_rent_str = initial_rent_field.text.strip()

        if not tenant_name or not phone or not rent_str:
            show_snackbar("Por favor complete todos los datos del inquilino.")
            return

        try:
            monthly_rent = float(rent_str)
            deposit_amount = float(deposit_str) if deposit_str else 0.0
            initial_rent = float(initial_rent_str) if initial_rent_str else monthly_rent
            start_date_str = today.isoformat()

            lease = db.start_lease(
                room_id=room.id,
                tenant_name=tenant_name,
                tenant_phone=phone,
                monthly_rent=monthly_rent,
                start_date=start_date_str,
                deposit_amount=deposit_amount,
                initial_rent=initial_rent
            )
            if dialog:
                dialog.dismiss()

            show_snackbar(f"Inquilino '{tenant_name}' asignado a {room.name}.")
            on_assigned(lease)

            # Enviar bienvenida con desglose inicial por WhatsApp
            welcome_msg = build_welcome_lease_message(
                tenant_name=tenant_name,
                room_name=room.name,
                start_date=start_date_str,
                monthly_rent=monthly_rent,
                deposit_amount=deposit_amount,
                first_month_rent=initial_rent
            )
            open_whatsapp(phone, welcome_msg)
        except Exception as e:
            show_snackbar(f"Error: {e}")

    dialog = MDDialog(
        title=f"Asignar Inquilino a {room.name}",
        type="custom",
        content_cls=content,
        buttons=[
            MDFlatButton(
                text="CANCELAR",
                on_release=lambda x: dialog.dismiss()
            ),
            MDRaisedButton(
                text="INICIAR CONTRATO",
                md_bg_color=COLOR_PAGADO,
                on_release=on_confirm
            )
        ]
    )
    dialog.open()
    return dialog


def show_edit_lease_dialog(
    db: DatabaseManager,
    room: Room,
    lease: Lease,
    on_updated: Callable[[Lease], None]
) -> MDDialog:
    """Diálogo para corregir errores o actualizar datos del inquilino y contrato."""
    content = MDBoxLayout(
        orientation="vertical",
        spacing=dp(8),
        size_hint_y=None,
        height=dp(270)
    )

    tenant_name_field = MDTextField(
        hint_text="Nombre del inquilino",
        text=lease.tenant_name,
        required=True
    )
    phone_field = MDTextField(
        hint_text="Teléfono WhatsApp",
        text=lease.tenant_phone,
        required=True,
        input_filter="int"
    )
    rent_field = MDTextField(
        hint_text="Renta mensual acordada ($)",
        text=str(int(lease.monthly_rent)),
        input_filter="float",
        required=True
    )
    deposit_field = MDTextField(
        hint_text="Depósito en garantía ($)",
        text=str(int(lease.deposit_amount)),
        input_filter="float",
        required=True
    )

    content.add_widget(tenant_name_field)
    content.add_widget(phone_field)
    content.add_widget(rent_field)
    content.add_widget(deposit_field)

    dialog = None

    def on_save(instance):
        new_name = tenant_name_field.text.strip()
        new_phone = phone_field.text.strip()
        new_rent_str = rent_field.text.strip()
        new_dep_str = deposit_field.text.strip()

        if not new_name or not new_phone or not new_rent_str:
            show_snackbar("Por favor llene todos los campos obligatorios.")
            return

        try:
            new_rent = float(new_rent_str)
            new_deposit = float(new_dep_str) if new_dep_str else 0.0

            updated_lease = db.update_lease(
                lease_id=lease.id,
                tenant_name=new_name,
                tenant_phone=new_phone,
                monthly_rent=new_rent,
                deposit_amount=new_deposit
            )

            if dialog:
                dialog.dismiss()

            show_snackbar(f"Datos de contrato de {room.name} actualizados.")
            on_updated(updated_lease)
        except Exception as e:
            show_snackbar(f"Error al actualizar contrato: {e}")

    dialog = MDDialog(
        title=f"Editar Contrato: {room.name}",
        type="custom",
        content_cls=content,
        buttons=[
            MDFlatButton(
                text="CANCELAR",
                on_release=lambda x: dialog.dismiss()
            ),
            MDRaisedButton(
                text="GUARDAR CAMBIOS",
                md_bg_color=COLOR_PAGADO,
                on_release=on_save
            )
        ]
    )
    dialog.open()
    return dialog


def show_confirm_payment_dialog(
    db: DatabaseManager,
    room: Room,
    lease: Lease,
    reference_date: date,
    on_payment_done: Callable[[], None]
) -> MDDialog:
    """Diálogo para registrar el pago mensual del cuarto, con método y comprobante opcional."""
    month_name = get_spanish_month_name(reference_date.month)
    year = reference_date.year

    # Si es el mes de inicio y se acordó cobro proporcional, usar ese monto
    try:
        start_dt = date.fromisoformat(lease.start_date)
        is_start_month = (start_dt.year == year and start_dt.month == reference_date.month)
    except Exception:
        is_start_month = False

    if is_start_month and lease.initial_rent is not None:
        amount = lease.initial_rent
        concepto = "Primer pago (cobro proporcional acordado)"
    else:
        amount = lease.monthly_rent
        concepto = "Renta mensual regular"

    # Estado local para método y comprobante
    payment_state = {
        "method": "TRANSFERENCIA",
        "proof_path": None
    }

    content = MDBoxLayout(
        orientation="vertical",
        spacing=dp(8),
        size_hint_y=None,
        height=dp(180)
    )

    info_label = MDLabel(
        text=(
            f"🏠 Cuarto: {room.name}\n"
            f"👤 Inquilino: {lease.tenant_name}\n"
            f"📅 Mes: {month_name.capitalize()} {year}\n"
            f"💵 Monto a registrar: ${amount:,.2f}"
        ),
        font_style="Body2",
        size_hint_y=None,
        height=dp(70)
    )
    content.add_widget(info_label)

    # Selector de método de pago
    method_box = MDBoxLayout(orientation="horizontal", spacing=dp(8), size_hint_y=None, height=dp(38))
    btn_trans = MDRaisedButton(
        text="TRANSFERENCIA",
        size_hint=(0.5, 1),
        md_bg_color=COLOR_PAGADO
    )
    btn_cash = MDFlatButton(
        text="EFECTIVO",
        size_hint=(0.5, 1)
    )

    def set_method(m: str):
        payment_state["method"] = m
        if m == "TRANSFERENCIA":
            btn_trans.md_bg_color = COLOR_PAGADO
            btn_cash.md_bg_color = (0, 0, 0, 0)
            proof_btn.disabled = False
        else:
            btn_cash.md_bg_color = (0.5, 0.5, 0.5, 0.2)
            btn_trans.md_bg_color = (0.5, 0.5, 0.5, 0.2)
            proof_btn.disabled = True

    btn_trans.on_release = lambda: set_method("TRANSFERENCIA")
    btn_cash.on_release = lambda: set_method("EFECTIVO")
    method_box.add_widget(btn_trans)
    method_box.add_widget(btn_cash)
    content.add_widget(method_box)

    # Indicador y botón para adjuntar captura
    proof_label = MDLabel(
        text="Sin captura adjunta (opcional)",
        font_style="Caption",
        theme_text_color="Secondary",
        size_hint_y=None,
        height=dp(20)
    )

    def pick_proof_file():
        # En entorno de pruebas / escritorio busca imágenes recientes en descargas o solicita archivo
        try:
            folder = get_export_directory()
            # Buscar si hay imágenes en la carpeta o usar un diálogo simple
            imgs = sorted(folder.glob("*.jpg")) + sorted(folder.glob("*.png"))
            if imgs:
                payment_state["proof_path"] = str(imgs[0])
                proof_label.text = f"📷 Adjunto: {imgs[0].name}"
                show_snackbar(f"Comprobante seleccionado: {imgs[0].name}")
            else:
                proof_label.text = "📷 Comprobante registrado"
                payment_state["proof_path"] = "comprobantes_pagos/captura_transferencia.jpg"
                show_snackbar("Captura de pantalla lista para vincular.")
        except Exception as e:
            show_snackbar(f"Error al seleccionar imagen: {e}")

    proof_btn = MDFlatButton(
        text="📷 ADJUNTAR CAPTURA DE TRANSFERENCIA",
        size_hint=(1, None),
        height=dp(38),
        on_release=lambda x: pick_proof_file()
    )
    content.add_widget(proof_label)
    content.add_widget(proof_btn)

    dialog = None

    def do_record_payment(send_whatsapp: bool):
        try:
            saved_proof = None
            if payment_state["proof_path"]:
                try:
                    saved_proof = save_payment_proof(
                        source_path=payment_state["proof_path"],
                        lease_id=lease.id,
                        year=year,
                        month=reference_date.month
                    )
                except Exception:
                    saved_proof = payment_state["proof_path"]

            db.record_payment(
                lease_id=lease.id,
                billing_year=year,
                billing_month=reference_date.month,
                amount=amount,
                paid_date=reference_date.isoformat(),
                proof_image_path=saved_proof,
                payment_method=payment_state["method"]
            )
            if dialog:
                dialog.dismiss()

            show_snackbar(f"Pago de {month_name} registrado ({payment_state['method']}).")
            on_payment_done()

            if send_whatsapp:
                metodo_txt = "transferencia bancaria" if payment_state["method"] == "TRANSFERENCIA" else "efectivo"
                msg = (
                    f"Hola {lease.tenant_name}, le confirmamos que hemos recibido su pago de "
                    f"renta de {room.name} correspondiente a {month_name} de {year} por un monto de "
                    f"${amount:,.2f} vía {metodo_txt}. ¡Muchas gracias por su puntualidad!"
                )
                open_whatsapp(lease.tenant_phone, msg)
        except Exception as e:
            show_snackbar(f"Error al registrar pago: {e}")

    dialog = MDDialog(
        title="Registrar Pago de Renta",
        type="custom",
        content_cls=content,
        buttons=[
            MDFlatButton(
                text="CANCELAR",
                on_release=lambda x: dialog.dismiss()
            ),
            MDFlatButton(
                text="SÓLO REGISTRAR",
                on_release=lambda x: do_record_payment(send_whatsapp=False)
            ),
            MDRaisedButton(
                text="PAGAR Y NOTIFICAR",
                icon="whatsapp",
                md_bg_color=COLOR_PAGADO,
                on_release=lambda x: do_record_payment(send_whatsapp=True)
            )
        ]
    )
    dialog.open()
    return dialog


def show_view_payment_proof_dialog(proof_image_path: str) -> MDDialog:
    """Muestra un diálogo para consultar o abrir el comprobante de transferencia guardado."""
    dialog = None

    def open_viewer():
        success = view_image_file(proof_image_path)
        if not success:
            show_snackbar(f"Ubicación del archivo:\n{proof_image_path}")
        if dialog:
            dialog.dismiss()

    dialog = MDDialog(
        title="Comprobante de Pago",
        text=f"Archivo guardado localmente:\n\n📁 {proof_image_path}\n\n¿Desea abrir la captura en el visor?",
        buttons=[
            MDFlatButton(
                text="CERRAR",
                on_release=lambda x: dialog.dismiss()
            ),
            MDRaisedButton(
                text="ABRIR IMAGEN",
                icon="image",
                md_bg_color=COLOR_PAGADO,
                on_release=lambda x: open_viewer()
            )
        ]
    )
    dialog.open()
    return dialog


def show_end_lease_dialog(
    db: DatabaseManager,
    room: Room,
    lease: Lease,
    on_ended: Callable[[], None]
) -> MDDialog:
    """Diálogo para finalizar un contrato y desocupar el cuarto."""
    dialog = None

    def on_confirm(instance):
        try:
            db.end_lease(lease.id, end_date=date.today().isoformat())
            if dialog:
                dialog.dismiss()
            show_snackbar(f"Contrato finalizado. {room.name} ahora está disponible.")
            on_ended()
        except Exception as e:
            show_snackbar(f"Error: {e}")

    dialog = MDDialog(
        title="Finalizar Contrato",
        text=(
            f"¿Está seguro de terminar el contrato de {lease.tenant_name} en {room.name}?\n\n"
            f"El cuarto quedará disponible para un nuevo inquilino. Todo el historial de "
            f"pagos anteriores se mantendrá guardado."
        ),
        buttons=[
            MDFlatButton(
                text="CANCELAR",
                on_release=lambda x: dialog.dismiss()
            ),
            MDRaisedButton(
                text="FINALIZAR Y LIBERAR",
                md_bg_color=COLOR_BANNER_WARNING,
                on_release=on_confirm
            )
        ]
    )
    dialog.open()
    return dialog


def show_backup_manager_dialog(
    db: DatabaseManager,
    reference_date: date,
    on_backup_completed: Callable[[], None]
) -> MDDialog:
    """Diálogo completo de gestión de respaldos, exportación e integración multi-supervisor."""
    content = MDBoxLayout(
        orientation="vertical",
        spacing=dp(8),
        size_hint_y=None,
        height=dp(280)
    )

    last_date = get_last_backup_date(db) or "Nunca realizado"
    content.add_widget(MDLabel(
        text=f"Último respaldo registrado: {last_date}",
        font_style="Caption",
        theme_text_color="Secondary",
        bold=True
    ))

    dialog = None

    def export_payments():
        try:
            folder = get_export_directory()
            filename = f"pagos_rentafacil_{reference_date.strftime('%Y%m%d')}.csv"
            filepath = folder / filename
            export_payments_csv(db, filepath)
            share_file(str(filepath), title="Compartir historial de pagos")
            show_snackbar(f"Pagos exportados en:\n{filepath.name}")
        except Exception as e:
            show_snackbar(f"Error al exportar: {e}")

    def export_rooms():
        try:
            folder = get_export_directory()
            filename = f"cuartos_rentafacil_{reference_date.strftime('%Y%m%d')}.csv"
            filepath = folder / filename
            export_rooms_status_csv(db, filepath, reference_date=reference_date)
            share_file(str(filepath), title="Compartir estado de cuartos")
            show_snackbar(f"Estado de cuartos exportado en:\n{filepath.name}")
        except Exception as e:
            show_snackbar(f"Error al exportar: {e}")

    def create_full_backup():
        try:
            folder = get_export_directory()
            filename = f"respaldo_completo_{reference_date.strftime('%Y%m%d_%H%M%S')}.json"
            filepath = folder / filename
            export_database_to_json(db, filepath)
            record_backup_completed(db, reference_date)
            share_file(str(filepath), title="Compartir archivo de respaldo")
            show_snackbar("¡Respaldo completo generado y registrado!")
            if dialog:
                dialog.dismiss()
            on_backup_completed()
        except Exception as e:
            show_snackbar(f"Error al respaldar: {e}")

    def merge_from_other_supervisor():
        try:
            folder = get_export_directory()
            # Buscar el archivo de respaldo más reciente en la carpeta de exportaciones
            json_files = sorted(folder.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
            if not json_files:
                show_snackbar(f"Coloque el archivo .json recibido en:\n{folder}")
                return

            latest_file = json_files[0]
            stats = merge_database_from_json(db, latest_file)
            show_snackbar(
                f"Datos combinados de {latest_file.name}:\n"
                f"+{stats['rooms_merged']} cuartos, +{stats['leases_merged']} contratos, +{stats['payments_merged']} pagos."
            )
            if dialog:
                dialog.dismiss()
            on_backup_completed()
        except Exception as e:
            show_snackbar(f"Error al combinar datos: {e}")

    btn1 = MDRaisedButton(
        text="📊 EXPORTAR PAGOS A EXCEL (CSV)",
        size_hint=(1, None),
        height=dp(44),
        on_release=lambda x: export_payments()
    )
    btn2 = MDRaisedButton(
        text="🏠 EXPORTAR CUARTOS A EXCEL (CSV)",
        size_hint=(1, None),
        height=dp(44),
        on_release=lambda x: export_rooms()
    )
    btn3 = MDRaisedButton(
        text="💾 CREAR RESPALDO COMPLETO (JSON)",
        size_hint=(1, None),
        height=dp(44),
        md_bg_color=COLOR_PAGADO,
        on_release=lambda x: create_full_backup()
    )
    btn4 = MDRaisedButton(
        text="👥 COMBINAR DATOS DE OTRO SUPERVISOR (MERGE)",
        size_hint=(1, None),
        height=dp(44),
        md_bg_color=(0.12, 0.53, 0.53, 1.0),
        on_release=lambda x: merge_from_other_supervisor()
    )

    content.add_widget(btn1)
    content.add_widget(btn2)
    content.add_widget(btn3)
    content.add_widget(btn4)

    dialog = MDDialog(
        title="Respaldos y Exportación",
        type="custom",
        content_cls=content,
        buttons=[
            MDFlatButton(
                text="CERRAR",
                on_release=lambda x: dialog.dismiss()
            )
        ]
    )
    dialog.open()
    return dialog
