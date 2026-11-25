from datetime import date
from pathlib import Path
from typing import Callable, Optional
from kivy.metrics import dp
from kivy.uix.image import Image
from kivymd.uix.dialog import MDDialog
from kivymd.uix.button import (
    MDFlatButton,
    MDRaisedButton,
    MDRectangleFlatIconButton,
    MDFillRoundFlatIconButton,
    MDIconButton
)
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.scrollview import MDScrollView
from kivymd.uix.textfield import MDTextField
from kivymd.uix.label import MDLabel
from kivymd.uix.snackbar import MDSnackbar

from core.models import Room, Lease, DepositDeduction
from core.database import DatabaseManager
from core.settlement_engine import (
    calculate_settlement,
    build_settlement_whatsapp_message,
    DEFAULT_DEDUCTION_CONCEPTS,
    STATUS_REFUND_TO_TENANT,
    STATUS_EXACT_BALANCE
)
from core.billing_engine import (
    get_spanish_month_name,
    calculate_proportional_rent,
    build_welcome_lease_message
)
from core.backup_manager import (
    export_payments_csv,
    export_rooms_status_csv,
    export_database_to_json,
    export_full_backup_zip,
    merge_database_from_json,
    record_backup_completed,
    get_last_backup_date
)
from ui.android_bridge import (
    get_export_directory,
    share_file,
    open_whatsapp,
    save_payment_proof,
    save_tenant_id_photo,
    pick_image_file,
    pick_json_file,
    capture_camera_photo,
    view_image_file
)
from ui.theme_config import COLOR_PAGADO, COLOR_BANNER_WARNING


def show_snackbar(text: str) -> None:
    """Muestra un mensaje emergente limpio separado del botón flotante."""
    snackbar = MDSnackbar(
        MDLabel(
            text=text,
            theme_text_color="Custom",
            text_color=(1, 1, 1, 1),
            bold=True,
            adaptive_height=True
        ),
        snackbar_x="12dp",
        snackbar_y="16dp",
        size_hint_x=0.92,
        duration=3
    )
    snackbar.open()


def show_image_viewer_dialog(title: str, image_path: str) -> MDDialog:
    """
    Visor emergente offline dentro de la app para consultar fotos de INE o comprobantes
    sin depender de apps externas ni Uri.fromFile en Android 7-14.
    """
    path_obj = Path(image_path)
    content = MDBoxLayout(
        orientation="vertical",
        spacing=dp(8),
        size_hint_y=None,
        height=dp(360) if path_obj.exists() else dp(120)
    )

    if path_obj.exists():
        img = Image(
            source=str(path_obj.resolve()),
            allow_stretch=True,
            keep_ratio=True,
            size_hint=(1, None),
            height=dp(310)
        )
        content.add_widget(img)
        content.add_widget(MDLabel(
            text=f"Archivo local: {path_obj.name}",
            font_style="Caption",
            theme_text_color="Secondary",
            adaptive_height=True
        ))
    else:
        content.add_widget(MDLabel(
            text=f"No se encontró el archivo en el dispositivo:\n{image_path}",
            font_style="Body2",
            theme_text_color="Secondary",
            adaptive_height=True
        ))

    dialog = None
    buttons = [
        MDFlatButton(
            text="CERRAR",
            on_release=lambda x: dialog.dismiss()
        )
    ]
    if path_obj.exists():
        buttons.append(
            MDFlatButton(
                text="ABRIR EXTERNO",
                on_release=lambda x: view_image_file(str(path_obj))
            )
        )

    dialog = MDDialog(
        title=title,
        type="custom",
        content_cls=content,
        buttons=buttons
    )
    dialog.open()
    return dialog


def show_new_room_dialog(db: DatabaseManager, on_created: Callable[[Room], None]) -> MDDialog:
    """Diálogo para registrar una nueva habitación."""
    content = MDBoxLayout(
        orientation="vertical",
        spacing=dp(12),
        size_hint_y=None,
        height=dp(145)
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
    """Diálogo deslizable para iniciar contrato con depósito, cobro proporcional e INE opcional."""
    today = date.today()
    suggested_initial_rent = calculate_proportional_rent(room.default_rent, today)

    scroll = MDScrollView(size_hint_y=None, height=dp(380), do_scroll_x=False)
    form_box = MDBoxLayout(
        orientation="vertical",
        spacing=dp(10),
        size_hint_y=None,
        adaptive_height=True,
        padding=[0, dp(4), 0, dp(8)]
    )

    tenant_name_field = MDTextField(
        hint_text="Nombre completo del inquilino",
        required=True,
        size_hint_y=None,
        height=dp(56)
    )
    phone_field = MDTextField(
        hint_text="Teléfono WhatsApp (ej. 5512345678)",
        required=True,
        input_filter="int",
        size_hint_y=None,
        height=dp(56)
    )
    rent_field = MDTextField(
        hint_text="Renta mensual regular ($)",
        text=str(int(room.default_rent)),
        input_filter="float",
        required=True,
        size_hint_y=None,
        height=dp(56)
    )
    deposit_field = MDTextField(
        hint_text="Depósito en garantía recibido ($)",
        text=str(int(room.default_rent)),
        input_filter="float",
        required=True,
        size_hint_y=None,
        height=dp(56)
    )

    helper_txt = "Cobro proporcional sugerido por días restantes" if today.day > 5 else "Cobro del primer mes completo"
    initial_rent_field = MDTextField(
        hint_text="Primer cobro acordado ($)",
        text=f"{suggested_initial_rent:.2f}",
        helper_text=helper_txt,
        helper_text_mode="persistent",
        input_filter="float",
        required=True,
        size_hint_y=None,
        height=dp(68)
    )

    id_state = {"front": None, "back": None}
    ine_status_label = MDLabel(
        text="Identificación (INE) opcional: sin fotos adjuntas",
        font_style="Caption",
        theme_text_color="Secondary",
        adaptive_height=True
    )

    def _refresh_ine_label():
        f_txt = "Frente listo" if id_state["front"] else "Sin frente"
        b_txt = "Reverso listo" if id_state["back"] else "Sin reverso"
        ine_status_label.text = f"INE (opcional): {f_txt} | {b_txt}"

    def _select_ine(side: str):
        def _on_picked(path: Optional[str]):
            if path:
                id_state[side] = path
                _refresh_ine_label()
                show_snackbar(f"Foto de INE ({'frente' if side == 'front' else 'reverso'}) adjuntada.")
        pick_image_file(_on_picked)

    ine_row = MDBoxLayout(orientation="horizontal", spacing=dp(8), size_hint_y=None, height=dp(42))
    ine_row.add_widget(MDRectangleFlatIconButton(
        text="INE FRENTE",
        icon="card-account-details-outline",
        size_hint=(0.5, 1),
        on_release=lambda x: _select_ine("front")
    ))
    ine_row.add_widget(MDRectangleFlatIconButton(
        text="INE REVERSO",
        icon="card-text-outline",
        size_hint=(0.5, 1),
        on_release=lambda x: _select_ine("back")
    ))

    form_box.add_widget(tenant_name_field)
    form_box.add_widget(phone_field)
    form_box.add_widget(rent_field)
    form_box.add_widget(deposit_field)
    form_box.add_widget(initial_rent_field)
    form_box.add_widget(ine_status_label)
    form_box.add_widget(ine_row)
    scroll.add_widget(form_box)

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

            # Comprimir y guardar fotos de INE si se adjuntaron
            front_saved = None
            back_saved = None
            if id_state["front"] and lease.id is not None:
                front_saved = save_tenant_id_photo(id_state["front"], lease.id, "frente")
            if id_state["back"] and lease.id is not None:
                back_saved = save_tenant_id_photo(id_state["back"], lease.id, "reverso")
            if front_saved or back_saved:
                lease = db.update_lease(
                    lease.id,
                    id_front_path=front_saved,
                    id_back_path=back_saved
                )

            if dialog:
                dialog.dismiss()

            show_snackbar(f"Inquilino '{tenant_name}' asignado a {room.name}.")
            on_assigned(lease)

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
        title=f"Asignar Inquilino: {room.name}",
        type="custom",
        content_cls=scroll,
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


def show_tenant_id_dialog(
    db: DatabaseManager,
    room: Room,
    lease: Lease,
    on_updated: Callable[[], None]
) -> MDDialog:
    """
    Diálogo dedicado para capturar, comprimir y consultar offline las fotos frontal y trasera
    de la identificación (INE / ID) del inquilino.
    """
    scroll = MDScrollView(size_hint_y=None, height=dp(320), do_scroll_x=False)
    content = MDBoxLayout(
        orientation="vertical",
        spacing=dp(12),
        size_hint_y=None,
        adaptive_height=True,
        padding=[0, dp(4), 0, dp(8)]
    )

    content.add_widget(MDLabel(
        text=f"Cuarto: {room.name}  |  Inquilino: {lease.tenant_name}",
        font_style="Body2",
        bold=True,
        adaptive_height=True
    ))

    state = {
        "front": lease.id_front_path,
        "back": lease.id_back_path
    }

    front_status = MDLabel(text="", font_style="Caption", theme_text_color="Secondary", adaptive_height=True)
    back_status = MDLabel(text="", font_style="Caption", theme_text_color="Secondary", adaptive_height=True)
    btn_view_front = MDIconButton(icon="eye-outline", size_hint=(None, None), size=(dp(36), dp(36)))
    btn_view_back = MDIconButton(icon="eye-outline", size_hint=(None, None), size=(dp(36), dp(36)))

    def refresh_labels():
        f_ok = bool(state["front"] and Path(state["front"]).exists())
        b_ok = bool(state["back"] and Path(state["back"]).exists())
        front_status.text = f"INE Frente: {'Guardada offline' if state['front'] else 'Pendiente'}"
        back_status.text = f"INE Reverso: {'Guardado offline' if state['back'] else 'Pendiente'}"
        btn_view_front.disabled = not bool(state["front"])
        btn_view_back.disabled = not bool(state["back"])
        if state["front"] and not f_ok:
            front_status.text = f"INE Frente: ruta registrada ({Path(state['front']).name})"
        if state["back"] and not b_ok:
            back_status.text = f"INE Reverso: ruta registrada ({Path(state['back']).name})"

    def handle_capture(side: str, use_camera: bool):
        def _save_from_path(src_path: Optional[str]):
            if not src_path:
                return
            try:
                saved = save_tenant_id_photo(src_path, lease.id, "frente" if side == "front" else "reverso")
                state[side] = saved
                if side == "front":
                    db.update_lease(lease.id, id_front_path=saved)
                else:
                    db.update_lease(lease.id, id_back_path=saved)
                refresh_labels()
                on_updated()
                show_snackbar(f"INE ({'frente' if side == 'front' else 'reverso'}) guardada y optimizada.")
            except Exception as e:
                show_snackbar(f"Error al guardar foto: {e}")

        if use_camera:
            ok = capture_camera_photo(_save_from_path, filename_prefix=f"ine_{lease.id}_{side}")
            if not ok:
                show_snackbar("Cámara no disponible en este equipo; use Galería.")
        else:
            pick_image_file(_save_from_path)

    btn_view_front.on_release = lambda: show_image_viewer_dialog(
        f"INE Frente - {lease.tenant_name}", state["front"]
    ) if state["front"] else None
    btn_view_back.on_release = lambda: show_image_viewer_dialog(
        f"INE Reverso - {lease.tenant_name}", state["back"]
    ) if state["back"] else None

    # Sección Frente
    front_header = MDBoxLayout(orientation="horizontal", size_hint_y=None, height=dp(36), spacing=dp(4))
    front_status.pos_hint = {"center_y": 0.5}
    front_header.add_widget(front_status)
    front_header.add_widget(btn_view_front)
    content.add_widget(front_header)

    front_row = MDBoxLayout(orientation="horizontal", spacing=dp(8), size_hint_y=None, height=dp(42))
    front_row.add_widget(MDFillRoundFlatIconButton(
        text="GALERÍA",
        icon="image-plus",
        size_hint=(0.5, 1),
        text_color=(1, 1, 1, 1),
        icon_color=(1, 1, 1, 1),
        on_release=lambda x: handle_capture("front", use_camera=False)
    ))
    front_row.add_widget(MDRectangleFlatIconButton(
        text="CÁMARA",
        icon="camera",
        size_hint=(0.5, 1),
        on_release=lambda x: handle_capture("front", use_camera=True)
    ))
    content.add_widget(front_row)

    # Sección Reverso
    back_header = MDBoxLayout(orientation="horizontal", size_hint_y=None, height=dp(36), spacing=dp(4))
    back_status.pos_hint = {"center_y": 0.5}
    back_header.add_widget(back_status)
    back_header.add_widget(btn_view_back)
    content.add_widget(back_header)

    back_row = MDBoxLayout(orientation="horizontal", spacing=dp(8), size_hint_y=None, height=dp(42))
    back_row.add_widget(MDFillRoundFlatIconButton(
        text="GALERÍA",
        icon="image-plus",
        size_hint=(0.5, 1),
        text_color=(1, 1, 1, 1),
        icon_color=(1, 1, 1, 1),
        on_release=lambda x: handle_capture("back", use_camera=False)
    ))
    back_row.add_widget(MDRectangleFlatIconButton(
        text="CÁMARA",
        icon="camera",
        size_hint=(0.5, 1),
        on_release=lambda x: handle_capture("back", use_camera=True)
    ))
    content.add_widget(back_row)

    refresh_labels()
    scroll.add_widget(content)

    dialog = None
    dialog = MDDialog(
        title="Identificación (INE / ID)",
        type="custom",
        content_cls=scroll,
        buttons=[
            MDFlatButton(
                text="CERRAR",
                on_release=lambda x: dialog.dismiss()
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
    """Diálogo deslizable para corregir datos del inquilino y contrato."""
    scroll = MDScrollView(size_hint_y=None, height=dp(300), do_scroll_x=False)
    content = MDBoxLayout(
        orientation="vertical",
        spacing=dp(10),
        size_hint_y=None,
        adaptive_height=True,
        padding=[0, dp(4), 0, dp(8)]
    )

    tenant_name_field = MDTextField(
        hint_text="Nombre del inquilino",
        text=lease.tenant_name,
        required=True,
        size_hint_y=None,
        height=dp(56)
    )
    phone_field = MDTextField(
        hint_text="Teléfono WhatsApp",
        text=lease.tenant_phone,
        required=True,
        input_filter="int",
        size_hint_y=None,
        height=dp(56)
    )
    rent_field = MDTextField(
        hint_text="Renta mensual acordada ($)",
        text=str(int(lease.monthly_rent)),
        input_filter="float",
        required=True,
        size_hint_y=None,
        height=dp(56)
    )
    deposit_field = MDTextField(
        hint_text="Depósito en garantía ($)",
        text=str(int(lease.deposit_amount)),
        input_filter="float",
        required=True,
        size_hint_y=None,
        height=dp(56)
    )

    content.add_widget(tenant_name_field)
    content.add_widget(phone_field)
    content.add_widget(rent_field)
    content.add_widget(deposit_field)
    scroll.add_widget(content)

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
        content_cls=scroll,
        buttons=[
            MDFlatButton(
                text="CANCELAR",
                on_release=lambda x: dialog.dismiss()
            ),
            MDRaisedButton(
                text="GUARDAR",
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

    try:
        start_dt = date.fromisoformat(lease.start_date)
        is_start_month = (start_dt.year == year and start_dt.month == reference_date.month)
    except Exception:
        is_start_month = False

    if is_start_month and lease.initial_rent is not None:
        amount = lease.initial_rent
    else:
        amount = lease.monthly_rent

    payment_state = {
        "method": "TRANSFERENCIA",
        "proof_path": None
    }

    scroll = MDScrollView(size_hint_y=None, height=dp(335), do_scroll_x=False)
    content = MDBoxLayout(
        orientation="vertical",
        spacing=dp(10),
        size_hint_y=None,
        adaptive_height=True,
        padding=[0, dp(4), 0, dp(4)]
    )

    info_label = MDLabel(
        text=(
            f"Cuarto: {room.name}\n"
            f"Inquilino: {lease.tenant_name}\n"
            f"Mes: {month_name.capitalize()} {year}\n"
            f"Monto a registrar: ${amount:,.2f}"
        ),
        font_style="Body2",
        adaptive_height=True
    )
    content.add_widget(info_label)

    # Selector de método de pago con contraste claro
    method_box = MDBoxLayout(orientation="horizontal", spacing=dp(8), size_hint_y=None, height=dp(42))
    btn_trans = MDRaisedButton(
        text="TRANSFERENCIA",
        size_hint=(0.5, 1),
        md_bg_color=COLOR_PAGADO,
        text_color=(1, 1, 1, 1)
    )
    btn_cash = MDRaisedButton(
        text="EFECTIVO",
        size_hint=(0.5, 1),
        md_bg_color=(0.88, 0.88, 0.88, 1),
        text_color=(0.2, 0.2, 0.2, 1)
    )

    proof_label = MDLabel(
        text="Sin captura adjunta (opcional)",
        font_style="Caption",
        theme_text_color="Secondary",
        adaptive_height=True
    )

    def pick_proof_file():
        def _on_picked(selected: Optional[str]):
            if selected:
                payment_state["proof_path"] = selected
                proof_label.text = f"Adjunto: {Path(selected).name}"
                show_snackbar(f"Comprobante seleccionado: {Path(selected).name}")
        pick_image_file(_on_picked)

    proof_btn = MDRectangleFlatIconButton(
        text="ADJUNTAR COMPROBANTE",
        icon="image-plus",
        size_hint=(1, None),
        height=dp(42),
        on_release=lambda x: pick_proof_file()
    )

    def set_method(m: str):
        payment_state["method"] = m
        if m == "TRANSFERENCIA":
            btn_trans.md_bg_color = COLOR_PAGADO
            btn_trans.text_color = (1, 1, 1, 1)
            btn_cash.md_bg_color = (0.88, 0.88, 0.88, 1)
            btn_cash.text_color = (0.2, 0.2, 0.2, 1)
            proof_btn.disabled = False
        else:
            btn_cash.md_bg_color = COLOR_PAGADO
            btn_cash.text_color = (1, 1, 1, 1)
            btn_trans.md_bg_color = (0.88, 0.88, 0.88, 1)
            btn_trans.text_color = (0.2, 0.2, 0.2, 1)
            proof_btn.disabled = True

    btn_trans.on_release = lambda: set_method("TRANSFERENCIA")
    btn_cash.on_release = lambda: set_method("EFECTIVO")
    method_box.add_widget(btn_trans)
    method_box.add_widget(btn_cash)
    content.add_widget(method_box)
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

    content.add_widget(MDFillRoundFlatIconButton(
        text="PAGAR Y NOTIFICAR WHATSAPP",
        icon="whatsapp",
        size_hint=(1, None),
        height=dp(44),
        md_bg_color=COLOR_PAGADO,
        text_color=(1, 1, 1, 1),
        icon_color=(1, 1, 1, 1),
        on_release=lambda x: do_record_payment(send_whatsapp=True)
    ))
    content.add_widget(MDRectangleFlatIconButton(
        text="SOLO REGISTRAR PAGO",
        icon="check-bold",
        size_hint=(1, None),
        height=dp(42),
        on_release=lambda x: do_record_payment(send_whatsapp=False)
    ))
    scroll.add_widget(content)

    dialog = MDDialog(
        title="Registrar Pago de Renta",
        type="custom",
        content_cls=scroll,
        buttons=[
            MDFlatButton(
                text="CANCELAR",
                on_release=lambda x: dialog.dismiss()
            )
        ]
    )
    dialog.open()
    return dialog


def show_view_payment_proof_dialog(proof_image_path: str) -> MDDialog:
    """Abre el visor offline integrado para consultar el comprobante de transferencia."""
    return show_image_viewer_dialog("Comprobante de Pago", proof_image_path)


def show_end_lease_dialog(
    db: DatabaseManager,
    room: Room,
    lease: Lease,
    on_ended: Callable[[], None]
) -> MDDialog:
    """
    Diálogo interactivo deslizable para liquidar depósito, elegir conceptos predefinidos o personalizados,
    quitar deducciones y finalizar contrato con finiquito WhatsApp.
    """
    scroll = MDScrollView(size_hint_y=None, height=dp(400), do_scroll_x=False)
    content = MDBoxLayout(
        orientation="vertical",
        spacing=dp(10),
        size_hint_y=None,
        adaptive_height=True,
        padding=[0, dp(4), 0, dp(8)]
    )

    deposit_val = float(lease.deposit_amount or 0.0)
    deductions_list: list = []

    header = MDLabel(
        text=(
            f"[b]{room.name}[/b]  |  Inquilino: [b]{lease.tenant_name}[/b]\n"
            f"Depósito en garantía: [b]${deposit_val:,.2f}[/b]"
        ),
        markup=True,
        theme_text_color="Primary",
        font_style="Body2",
        adaptive_height=True
    )
    content.add_widget(header)

    concept_input = MDTextField(
        hint_text="Concepto deducción (ej. Pintura, Llaves)",
        text="",
        size_hint_y=None,
        height=dp(52)
    )
    content.add_widget(concept_input)

    # Botones rápidos de conceptos frecuentes (DEFAULT_DEDUCTION_CONCEPTS)
    presets_label = MDLabel(
        text="Conceptos rápidos (toque para rellenar):",
        font_style="Caption",
        theme_text_color="Secondary",
        adaptive_height=True
    )
    content.add_widget(presets_label)

    presets_box = MDBoxLayout(
        orientation="vertical",
        spacing=dp(4),
        size_hint_y=None,
        adaptive_height=True
    )
    for preset in DEFAULT_DEDUCTION_CONCEPTS[:4]:
        presets_box.add_widget(MDFlatButton(
            text=f"+ {preset}",
            theme_text_color="Primary",
            size_hint=(1, None),
            height=dp(32),
            on_release=lambda x, c=preset: setattr(concept_input, "text", c)
        ))
    content.add_widget(presets_box)

    amount_input = MDTextField(
        hint_text="Monto a deducir ($)",
        text="",
        input_filter="float",
        size_hint_y=None,
        height=dp(52)
    )
    content.add_widget(amount_input)

    summary_label = MDLabel(
        text=f"Saldo a devolver al inquilino: ${deposit_val:,.2f}",
        bold=True,
        theme_text_color="Custom",
        text_color=COLOR_PAGADO,
        font_style="Subtitle2",
        adaptive_height=True
    )

    deductions_list_box = MDBoxLayout(
        orientation="vertical",
        spacing=dp(4),
        size_hint_y=None,
        adaptive_height=True
    )

    def remove_deduction(idx: int):
        if 0 <= idx < len(deductions_list):
            removed = deductions_list.pop(idx)
            update_balance_display()
            show_snackbar(f"Deducción eliminada: {removed.concept}")

    def update_balance_display():
        calc = calculate_settlement(deposit_val, deductions_list)
        ref = calc["refund_amount"]
        if calc["status"] == STATUS_REFUND_TO_TENANT:
            summary_label.text = f"Saldo a devolver al inquilino: ${ref:,.2f}"
            summary_label.text_color = COLOR_PAGADO
        elif calc["status"] == STATUS_EXACT_BALANCE:
            summary_label.text = "Cuentas saldadas ($0.00)"
            summary_label.text_color = (0.2, 0.5, 0.8, 1.0)
        else:
            summary_label.text = f"Inquilino adeuda: ${calc['balance_due_by_tenant']:,.2f}"
            summary_label.text_color = COLOR_BANNER_WARNING

        deductions_list_box.clear_widgets()
        if not deductions_list:
            deductions_list_box.add_widget(MDLabel(
                text="Sin deducciones aplicadas (depósito íntegro).",
                theme_text_color="Secondary",
                font_style="Caption",
                adaptive_height=True
            ))
        else:
            for idx, d in enumerate(deductions_list):
                row = MDBoxLayout(orientation="horizontal", size_hint_y=None, height=dp(32), spacing=dp(4))
                row.add_widget(MDLabel(
                    text=f"• {d.concept}: -${d.amount:,.2f}",
                    font_style="Caption",
                    theme_text_color="Primary",
                    pos_hint={"center_y": 0.5}
                ))
                row.add_widget(MDIconButton(
                    icon="close-circle-outline",
                    size_hint=(None, None),
                    size=(dp(28), dp(28)),
                    pos_hint={"center_y": 0.5},
                    on_release=lambda x, i=idx: remove_deduction(i)
                ))
                deductions_list_box.add_widget(row)

    def add_deduction_item():
        c_text = concept_input.text.strip()
        a_text = amount_input.text.strip()
        if not c_text:
            show_snackbar("Escriba el concepto de la deducción.")
            return
        try:
            val = float(a_text)
            if val <= 0:
                show_snackbar("El monto debe ser mayor a 0.")
                return
            deductions_list.append(DepositDeduction(concept=c_text, amount=val))
            concept_input.text = ""
            amount_input.text = ""
            update_balance_display()
            show_snackbar(f"Deducción agregada: {c_text} (-${val:,.2f})")
        except ValueError:
            show_snackbar("Ingrese un monto numérico válido.")

    btn_add_deduction = MDRectangleFlatIconButton(
        text="AGREGAR DEDUCCIÓN",
        icon="plus-circle-outline",
        size_hint=(1, None),
        height=dp(40),
        on_release=lambda x: add_deduction_item()
    )
    content.add_widget(btn_add_deduction)
    content.add_widget(summary_label)
    update_balance_display()
    content.add_widget(deductions_list_box)

    notes_input = MDTextField(
        hint_text="Observaciones de entrega (opcional)",
        text="",
        size_hint_y=None,
        height=dp(52)
    )
    content.add_widget(notes_input)

    dialog = None

    def execute_settlement(send_whatsapp: bool):
        try:
            today_dt = date.today()
            today_str = today_dt.isoformat()
            notes_val = notes_input.text.strip() or None
            db.finalize_lease_with_settlement(
                lease_id=lease.id,
                settlement_date=today_str,
                deposit_total=deposit_val,
                deductions=deductions_list,
                notes=notes_val
            )

            if dialog:
                dialog.dismiss()

            show_snackbar(f"Contrato finalizado y finiquito guardado. {room.name} ahora está disponible.")
            on_ended()

            if send_whatsapp:
                msg = build_settlement_whatsapp_message(
                    tenant_name=lease.tenant_name,
                    room_name=room.name,
                    settlement_date=today_dt,
                    deposit_total=deposit_val,
                    deductions=deductions_list,
                    notes=notes_val
                )
                open_whatsapp(lease.tenant_phone, msg)
        except Exception as e:
            show_snackbar(f"Error al liquidar contrato: {e}")

    content.add_widget(MDFillRoundFlatIconButton(
        text="FINALIZAR Y ENVIAR WHATSAPP",
        icon="whatsapp",
        size_hint=(1, None),
        height=dp(44),
        md_bg_color=COLOR_PAGADO,
        text_color=(1, 1, 1, 1),
        icon_color=(1, 1, 1, 1),
        on_release=lambda x: execute_settlement(send_whatsapp=True)
    ))
    content.add_widget(MDRectangleFlatIconButton(
        text="FINALIZAR SIN WHATSAPP",
        icon="check-circle-outline",
        size_hint=(1, None),
        height=dp(42),
        text_color=COLOR_BANNER_WARNING,
        line_color=COLOR_BANNER_WARNING,
        icon_color=COLOR_BANNER_WARNING,
        on_release=lambda x: execute_settlement(send_whatsapp=False)
    ))
    scroll.add_widget(content)

    dialog = MDDialog(
        title="Finiquito y Entrega de Cuarto",
        type="custom",
        content_cls=scroll,
        buttons=[
            MDFlatButton(
                text="CANCELAR",
                on_release=lambda x: dialog.dismiss()
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
    """Diálogo compacto de respaldos con ZIP+imágenes, CSV para contadores, y merge por selector de archivos."""

    inner = MDBoxLayout(
        orientation="vertical",
        spacing=dp(8),
        size_hint_y=None,
        adaptive_height=True,
        padding=[0, 0, 0, dp(4)]
    )

    last_date = get_last_backup_date(db) or "Nunca"
    inner.add_widget(MDLabel(
        text=f"Último respaldo: {last_date}",
        font_style="Caption",
        theme_text_color="Secondary",
        bold=True,
        adaptive_height=True
    ))

    dialog = None

    # --- Sección 1: Respaldo completo (ZIP con imágenes) ---
    inner.add_widget(_section_label("RESPALDO COMPLETO"))

    def create_zip_backup():
        try:
            folder = get_export_directory()
            ts = reference_date.strftime('%Y%m%d_%H%M%S')
            filepath = folder / f"respaldo_rentalo_{ts}.zip"
            export_full_backup_zip(db, filepath, reference_date)
            record_backup_completed(db, reference_date)
            share_file(str(filepath), mime_type="application/zip",
                       title="Enviar respaldo por WhatsApp")
            show_snackbar("Respaldo ZIP con imágenes generado.")
            if dialog:
                dialog.dismiss()
            on_backup_completed()
        except Exception as e:
            show_snackbar(f"Error al respaldar: {e}")

    btn_zip = MDFillRoundFlatIconButton(
        text="RESPALDAR TODO (ZIP)",
        icon="zip-box-outline",
        size_hint=(1, None),
        height=dp(44),
        md_bg_color=COLOR_PAGADO,
        text_color=(1, 1, 1, 1),
        icon_color=(1, 1, 1, 1),
        on_release=lambda x: create_zip_backup()
    )
    inner.add_widget(btn_zip)
    inner.add_widget(MDLabel(
        text="Incluye datos + fotos INE y comprobantes.\nEnvíelo por WhatsApp al otro supervisor.",
        font_style="Caption",
        theme_text_color="Hint",
        adaptive_height=True
    ))

    # --- Sección 2: Combinar datos recibidos ---
    inner.add_widget(_section_label("COMBINAR DATOS"))

    def merge_from_file():
        def _on_file_selected(path: str | None):
            if not path:
                show_snackbar("No se seleccionó ningún archivo.")
                return
            try:
                stats = merge_database_from_json(db, path)
                show_snackbar(
                    f"Datos combinados:\n"
                    f"+{stats['rooms_merged']} cuartos, +{stats['leases_merged']} contratos, "
                    f"+{stats['payments_merged']} pagos, +{stats.get('settlements_merged', 0)} finiquitos."
                )
                if dialog:
                    dialog.dismiss()
                on_backup_completed()
            except Exception as e:
                show_snackbar(f"Error al combinar: {e}")
        pick_json_file(_on_file_selected)

    btn_merge = MDFillRoundFlatIconButton(
        text="IMPORTAR ARCHIVO .JSON",
        icon="file-import-outline",
        size_hint=(1, None),
        height=dp(44),
        md_bg_color=(0.12, 0.53, 0.53, 1.0),
        text_color=(1, 1, 1, 1),
        icon_color=(1, 1, 1, 1),
        on_release=lambda x: merge_from_file()
    )
    inner.add_widget(btn_merge)
    inner.add_widget(MDLabel(
        text="Seleccione el .json recibido por WhatsApp\no descargado de otro dispositivo.",
        font_style="Caption",
        theme_text_color="Hint",
        adaptive_height=True
    ))

    # --- Sección 3: Exportar CSV para Excel / contador ---
    inner.add_widget(_section_label("EXPORTAR PARA EXCEL"))

    def export_payments():
        try:
            folder = get_export_directory()
            filename = f"pagos_rentalo_{reference_date.strftime('%Y%m%d')}.csv"
            filepath = folder / filename
            export_payments_csv(db, filepath)
            share_file(str(filepath), mime_type="text/csv",
                       title="Enviar historial de pagos")
            show_snackbar(f"CSV exportado. Ábralo en Excel o\nenvíelo al contador por WhatsApp.")
        except Exception as e:
            show_snackbar(f"Error al exportar: {e}")

    def export_rooms():
        try:
            folder = get_export_directory()
            filename = f"cuartos_rentalo_{reference_date.strftime('%Y%m%d')}.csv"
            filepath = folder / filename
            export_rooms_status_csv(db, filepath, reference_date=reference_date)
            share_file(str(filepath), mime_type="text/csv",
                       title="Enviar estado de cuartos")
            show_snackbar(f"CSV exportado. Ábralo en Excel o\nenvíelo al contador por WhatsApp.")
        except Exception as e:
            show_snackbar(f"Error al exportar: {e}")

    csv_row = MDBoxLayout(
        orientation="horizontal",
        spacing=dp(8),
        size_hint_y=None,
        height=dp(44)
    )
    btn_csv_pagos = MDRectangleFlatIconButton(
        text="PAGOS",
        icon="file-excel-outline",
        size_hint=(0.5, None),
        height=dp(44),
        on_release=lambda x: export_payments()
    )
    btn_csv_cuartos = MDRectangleFlatIconButton(
        text="CUARTOS",
        icon="home-export-outline",
        size_hint=(0.5, None),
        height=dp(44),
        on_release=lambda x: export_rooms()
    )
    csv_row.add_widget(btn_csv_pagos)
    csv_row.add_widget(btn_csv_cuartos)
    inner.add_widget(csv_row)
    inner.add_widget(MDLabel(
        text="Para abrir en computadora con Excel o Google Sheets.",
        font_style="Caption",
        theme_text_color="Hint",
        adaptive_height=True
    ))

    scroll = MDScrollView(size_hint_y=None, height=dp(380))
    scroll.add_widget(inner)

    dialog = MDDialog(
        title="Respaldos y Exportación",
        type="custom",
        content_cls=scroll,
        buttons=[
            MDFlatButton(
                text="CERRAR",
                on_release=lambda x: dialog.dismiss()
            )
        ]
    )
    dialog.open()
    return dialog


def _section_label(text: str) -> MDLabel:
    """Crea un encabezado de sección pequeño para el diálogo de respaldos."""
    return MDLabel(
        text=text,
        font_style="Overline",
        theme_text_color="Primary",
        bold=True,
        adaptive_height=True
    )
