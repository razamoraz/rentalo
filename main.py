import os
import sys
from datetime import date
from pathlib import Path
from typing import Optional, List

# Configurar tamaño de ventana para emular pantalla de teléfono en pruebas de escritorio
from kivy.config import Config
Config.set('graphics', 'width', '420')
Config.set('graphics', 'height', '780')

from kivy.metrics import dp
from kivy.core.window import Window
from kivymd.app import MDApp
from kivymd.uix.screen import MDScreen
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.toolbar import MDTopAppBar
from kivymd.uix.scrollview import MDScrollView
from kivymd.uix.button import MDFloatingActionButton
from kivymd.uix.label import MDLabel
from kivymd.uix.card import MDCard
from kivymd.uix.dialog import MDDialog
from kivymd.uix.list import MDList, OneLineIconListItem, IconLeftWidget
from kivymd.uix.button import MDFlatButton, MDRaisedButton

from core.database import DatabaseManager
from core.models import Room, Lease, Payment
from core.billing_engine import (
    get_payment_status,
    get_spanish_month_name,
    STATUS_PAGADO,
    STATUS_PENDIENTE,
    STATUS_ATRASADO,
    get_whatsapp_payment_link
)
from core.backup_manager import (
    is_backup_overdue,
    record_backup_completed
)
from core.settlement_engine import build_house_rules_whatsapp_message
from ui.theme_config import (
    COLOR_PAGADO,
    COLOR_PENDIENTE,
    COLOR_ATRASADO,
    COLOR_DISPONIBLE,
    STATUS_DISPONIBLE,
    COLOR_BANNER_WARNING
)
from ui.components import BackupWarningBanner, RoomCard
from ui.dialogs import (
    show_new_room_dialog,
    show_assign_tenant_dialog,
    show_tenant_id_dialog,
    show_confirm_payment_dialog,
    show_view_payment_proof_dialog,
    show_edit_lease_dialog,
    show_end_lease_dialog,
    show_backup_manager_dialog,
    show_snackbar
)
from core.notifications import (
    get_monthly_reminder_status,
    mark_notification_sent
)
from ui.android_bridge import open_whatsapp, send_local_notification


class RenTaloApp(MDApp):
    def __init__(self, db_path: Optional[str] = None, **kwargs):
        super().__init__(**kwargs)
        self.title = "renTalo"
        # Ruta de base de datos configurable (útil para pruebas y producción)
        if db_path is None:
            if Path("rentalo.db").exists() or not Path("rentafacil.db").exists():
                db_file = Path("rentalo.db")
            else:
                db_file = Path("rentafacil.db")
        else:
            db_file = Path(db_path)
        self.db = DatabaseManager(db_file)
        self.reference_date: date = date.today()

    def build(self):
        self.theme_cls.primary_palette = "Teal"
        self.theme_cls.accent_palette = "Amber"
        self.theme_cls.theme_style = "Light"

        # Pantalla principal
        self.root_screen = MDScreen()
        main_layout = MDBoxLayout(orientation="vertical")

        # 1. Barra superior de navegación y título
        month_name = get_spanish_month_name(self.reference_date.month).capitalize()
        year = self.reference_date.year
        self.top_bar = MDTopAppBar(
            title=f"renTalo - {month_name} {year}",
            anchor_title="left",
            elevation=2,
            right_action_items=[
                ["cloud-upload-outline", lambda x: self.open_backup_dialog(), "Respaldos y Excel"],
                ["plus-circle-outline", lambda x: self.open_new_room_dialog(), "Nuevo Cuarto"]
            ]
        )
        main_layout.add_widget(self.top_bar)

        # 2. Contenedor de contenido desplazable
        scroll = MDScrollView(do_scroll_x=False)
        self.content_layout = MDBoxLayout(
            orientation="vertical",
            padding=[dp(14), dp(12), dp(14), dp(80)],
            spacing=dp(12),
            size_hint_y=None
        )
        self.content_layout.bind(minimum_height=self.content_layout.setter('height'))
        scroll.add_widget(self.content_layout)
        main_layout.add_widget(scroll)

        self.root_screen.add_widget(main_layout)

        # 3. Botón flotante para agregar cuartos (FAB accesible para el operador)
        self.fab = MDFloatingActionButton(
            icon="plus",
            md_bg_color=self.theme_cls.primary_color,
            pos_hint={"right": 0.95, "y": 0.03},
            on_release=lambda x: self.open_new_room_dialog()
        )
        self.root_screen.add_widget(self.fab)

        # Inicializar datos muestra si la base de datos está vacía
        self._seed_sample_data_if_empty()

        # Cargar tarjetas y banner
        self.refresh_ui()

        # Comprobar recordatorios locales mensuales
        self.check_monthly_notifications()

        return self.root_screen

    def check_monthly_notifications(self) -> None:
        """Verifica y envía recordatorios locales mensuales si corresponde."""
        reminder = get_monthly_reminder_status(self.db, self.reference_date)
        if reminder:
            send_local_notification(reminder["title"], reminder["message"])
            mark_notification_sent(self.db, self.reference_date, reminder["type"])

    def _seed_sample_data_if_empty(self) -> None:
        """Crea habitaciones de demostración si la base de datos está recién creada."""
        rooms = self.db.get_all_rooms()
        if len(rooms) == 0:
            r1 = self.db.create_room("Cuarto 1 - Planta Baja", 2800.0)
            r2 = self.db.create_room("Cuarto 2 - Planta Alta", 3200.0)
            r3 = self.db.create_room("Cuarto 3 - Exterior", 2500.0)
            # Asignar un inquilino de muestra
            self.db.start_lease(
                room_id=r1.id,
                tenant_name="Juan Carlos Pérez",
                tenant_phone="5215512345678",
                monthly_rent=2800.0,
                start_date=self.reference_date.isoformat(),
                deposit_amount=2800.0,
                initial_rent=2800.0
            )

    def refresh_ui(self) -> None:
        """Recarga todas las tarjetas de cuartos, el resumen numérico y el banner de respaldo."""
        self.content_layout.clear_widgets()

        # A) Banner de respaldo si han pasado más de 180 días (o nunca se ha hecho)
        if is_backup_overdue(self.db, self.reference_date, days=180):
            banner = BackupWarningBanner(on_backup_click=self.open_backup_dialog)
            self.content_layout.add_widget(banner)

        # B) Resumen estadístico
        rooms = self.db.get_all_rooms()
        leases = {l.room_id: l for l in self.db.get_all_leases(active_only=True)}
        payments = self.db.get_all_payments()

        total_rooms = len(rooms)
        occupied_count = sum(1 for r in rooms if r.is_occupied)
        paid_count = 0
        pending_count = 0

        card_data = []
        for room in rooms:
            lease = leases.get(room.id)
            if lease:
                room_payments = [p for p in payments if p.lease_id == lease.id]
                status = get_payment_status(lease, room_payments, self.reference_date)
                cur_payment = next(
                    (p for p in room_payments if p.billing_year == self.reference_date.year and p.billing_month == self.reference_date.month),
                    None
                )
                if status == STATUS_PAGADO:
                    paid_count += 1
                else:
                    pending_count += 1
            else:
                status = STATUS_DISPONIBLE
                cur_payment = None

            card_data.append((room, lease, status, cur_payment))

        # Tarjeta de resumen rápido
        summary_card = MDCard(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(50),
            padding=[dp(12), dp(8), dp(12), dp(8)],
            spacing=dp(10),
            radius=[dp(10)],
            elevation=1
        )
        summary_card.add_widget(MDLabel(
            text=f"Total: {total_rooms}  |  Ocupados: {occupied_count}  |  Pagados: {paid_count}",
            bold=True,
            font_style="Caption",
            theme_text_color="Primary"
        ))
        self.content_layout.add_widget(summary_card)

        # C) Tarjetas de habitaciones
        for room, lease, status, cur_payment in card_data:
            card = RoomCard(
                room=room,
                lease=lease,
                status=status,
                current_day=self.reference_date.day,
                payment=cur_payment,
                on_pay_click=self.on_pay_room,
                on_whatsapp_click=self.on_send_whatsapp,
                on_assign_click=self.on_assign_room,
                on_menu_click=self.on_room_menu,
                on_view_proof=self.on_view_proof
            )
            self.content_layout.add_widget(card)

    def on_view_proof(self, proof_path: str) -> None:
        """Abre el diálogo para consultar el comprobante de pago."""
        show_view_payment_proof_dialog(proof_path)

    def on_pay_room(self, room: Room, lease: Lease) -> None:
        """Abre el diálogo para registrar el pago."""
        show_confirm_payment_dialog(
            db=self.db,
            room=room,
            lease=lease,
            reference_date=self.reference_date,
            on_payment_done=self.refresh_ui
        )

    def on_send_whatsapp(self, room: Room, lease: Lease, status: str) -> None:
        """Abre WhatsApp con el mensaje preformateado."""
        link = get_whatsapp_payment_link(
            lease=lease,
            room_name=room.name,
            reference_date=self.reference_date,
            amount=lease.monthly_rent,
            status=status
        )
        # Extraer el texto decodificado para pasarlo a open_whatsapp
        import urllib.parse
        parsed = urllib.parse.urlparse(link)
        params = urllib.parse.parse_qs(parsed.query)
        message = params.get("text", [""])[0]

        success = open_whatsapp(lease.tenant_phone, message)
        if success:
            show_snackbar(f"Abriendo WhatsApp para {lease.tenant_name}...")
        else:
            show_snackbar("No se pudo abrir WhatsApp.")

    def on_assign_room(self, room: Room) -> None:
        """Abre el diálogo para asignar un inquilino."""
        show_assign_tenant_dialog(
            db=self.db,
            room=room,
            on_assigned=lambda l: self.refresh_ui()
        )

    def on_send_house_rules(self, lease: Lease) -> None:
        """Abre WhatsApp con el reglamento interno de la casa para el inquilino."""
        msg = build_house_rules_whatsapp_message(tenant_name=lease.tenant_name, house_name="renTalo")
        success = open_whatsapp(lease.tenant_phone, msg)
        if success:
            show_snackbar(f"Abriendo WhatsApp con reglamento para {lease.tenant_name}...")
        else:
            show_snackbar("No se pudo abrir WhatsApp.")

    def on_room_menu(self, room: Room, lease: Optional[Lease]) -> None:
        """Menú vertical de opciones adicionales para el cuarto (sin desbordamiento en móvil)."""
        dialog = None
        menu_list = MDList()

        def _add_option(text: str, icon: str, callback):
            item = OneLineIconListItem(
                text=text,
                on_release=lambda x: [dialog.dismiss(), callback()]
            )
            item.add_widget(IconLeftWidget(icon=icon))
            menu_list.add_widget(item)

        if lease:
            _add_option(
                "Editar contrato",
                "account-edit-outline",
                lambda: show_edit_lease_dialog(self.db, room, lease, lambda l: self.refresh_ui())
            )
            _add_option(
                "Identificación (INE / ID)",
                "card-account-details-outline",
                lambda: show_tenant_id_dialog(self.db, room, lease, self.refresh_ui)
            )
            _add_option(
                "Reglamento interno (WhatsApp)",
                "file-document-outline",
                lambda: self.on_send_house_rules(lease)
            )
            _add_option(
                "Finalizar contrato y finiquito",
                "cash-check",
                lambda: show_end_lease_dialog(self.db, room, lease, self.refresh_ui)
            )

        _add_option(
            "Eliminar cuarto",
            "delete-outline",
            lambda: self._confirm_delete_room(None, room)
        )

        scroll_height = dp(245) if lease else dp(65)
        scroll = MDScrollView(size_hint_y=None, height=scroll_height, do_scroll_x=False)
        scroll.add_widget(menu_list)

        dialog = MDDialog(
            title=f"Opciones: {room.name}",
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

    def _confirm_delete_room(self, parent_dialog: Optional[MDDialog], room: Room) -> None:
        if parent_dialog:
            parent_dialog.dismiss()

        del_dialog = None

        def do_delete(instance):
            try:
                self.db.delete_room(room.id)
                del_dialog.dismiss()
                show_snackbar(f"Cuarto '{room.name}' eliminado.")
                self.refresh_ui()
            except Exception as e:
                show_snackbar(f"Error al eliminar: {e}")

        del_dialog = MDDialog(
            title="Eliminar Cuarto",
            text=f"¿Está seguro de eliminar '{room.name}'? Se eliminarán también sus contratos e historial.",
            buttons=[
                MDFlatButton(text="CANCELAR", on_release=lambda x: del_dialog.dismiss()),
                MDRaisedButton(text="ELIMINAR", md_bg_color=COLOR_BANNER_WARNING, on_release=do_delete)
            ]
        )
        del_dialog.open()

    def open_new_room_dialog(self) -> None:
        """Abre el diálogo para registrar un nuevo cuarto."""
        show_new_room_dialog(self.db, on_created=lambda r: self.refresh_ui())

    def open_backup_dialog(self) -> None:
        """Abre la pantalla de respaldos y exportación."""
        show_backup_manager_dialog(
            db=self.db,
            reference_date=self.reference_date,
            on_backup_completed=self.refresh_ui
        )


# Alias para compatibilidad hacia atrás
RentaFacilApp = RenTaloApp


if __name__ == "__main__":
    app = RenTaloApp()
    app.run()
