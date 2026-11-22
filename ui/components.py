from typing import Optional, Callable
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.card import MDCard
from kivymd.uix.label import MDLabel, MDIcon
from kivymd.uix.button import (
    MDRaisedButton,
    MDFillRoundFlatButton,
    MDFlatButton,
    MDIconButton
)

from core.models import Room, Lease, Payment
from core.billing_engine import (
    STATUS_PAGADO,
    STATUS_PENDIENTE,
    STATUS_ATRASADO,
    get_spanish_month_name
)
from ui.theme_config import (
    COLOR_PAGADO,
    COLOR_PENDIENTE,
    COLOR_ATRASADO,
    COLOR_DISPONIBLE,
    COLOR_BANNER_WARNING,
    BUTTON_HEIGHT,
    STATUS_DISPONIBLE,
    get_status_theme
)


class BackupWarningBanner(MDCard):
    """
    Banner de advertencia prominente que se muestra en la parte superior cuando
    han transcurrido 6 meses (180 días) sin realizar un respaldo de la base de datos.
    """
    def __init__(self, on_backup_click: Callable[[], None], **kwargs):
        super().__init__(**kwargs)
        self.orientation = "vertical"
        self.size_hint_y = None
        self.height = dp(110)
        self.padding = [dp(16), dp(12), dp(16), dp(12)]
        self.spacing = dp(8)
        self.radius = [dp(12)]
        self.elevation = 3
        self.md_bg_color = COLOR_BANNER_WARNING

        # Fila del mensaje con icono de alerta
        msg_layout = MDBoxLayout(
            orientation="horizontal",
            spacing=dp(10),
            size_hint_y=None,
            height=dp(40)
        )

        icon = MDIcon(
            icon="alert-octagon",
            theme_text_color="Custom",
            text_color=(1, 1, 1, 1),
            size_hint=(None, None),
            size=(dp(36), dp(36))
        )

        label = MDLabel(
            text="¡ALERTA DE SEGURIDAD!\nHace más de 6 meses no realiza un respaldo.",
            theme_text_color="Custom",
            text_color=(1, 1, 1, 1),
            bold=True,
            font_style="Subtitle2"
        )

        msg_layout.add_widget(icon)
        msg_layout.add_widget(label)
        self.add_widget(msg_layout)

        # Botón de acción grande
        btn = MDRaisedButton(
            text="RESPALDAR AHORA MISMO",
            md_bg_color=(1, 1, 1, 1),
            text_color=COLOR_BANNER_WARNING,
            size_hint=(1, None),
            height=dp(44),
            on_release=lambda x: on_backup_click()
        )
        self.add_widget(btn)


class StatusBadge(MDBoxLayout):
    """
    Insignia de estado con color, icono y texto grande.
    """
    def __init__(self, status: str, day_number: Optional[int] = None, **kwargs):
        super().__init__(**kwargs)
        self.orientation = "horizontal"
        self.size_hint = (None, None)
        self.height = dp(36)
        self.padding = [dp(12), dp(4), dp(12), dp(4)]
        self.spacing = dp(6)
        self.radius = [dp(18)]

        theme = get_status_theme(status)
        self.md_bg_color = theme["color"]

        icon = MDIcon(
            icon=theme["icon"],
            theme_text_color="Custom",
            text_color=(1, 1, 1, 1),
            size_hint=(None, None),
            size=(dp(24), dp(24))
        )
        self.add_widget(icon)

        label_text = theme["label"]
        if status == STATUS_PENDIENTE and day_number is not None:
            label_text = f"PENDIENTE (Día {day_number} de 5)"
        elif status == STATUS_ATRASADO and day_number is not None:
            label_text = f"ATRASADO (Día {day_number})"

        text = MDLabel(
            text=label_text,
            theme_text_color="Custom",
            text_color=(1, 1, 1, 1),
            bold=True,
            font_style="Caption",
            size_hint_x=None
        )
        text.bind(texture_size=lambda instance, value: setattr(instance, 'width', value[0]))
        self.add_widget(text)

        # Ajustar ancho del badge automáticamente
        self.width = dp(60) + (len(label_text) * dp(8))


class RoomCard(MDCard):
    """
    Tarjeta de habitación codificada por color con objetivos táctiles amplios (mínimo 48-52dp)
    para uso cómodo por parte de operadores no técnicos en Android.
    """
    def __init__(
        self,
        room: Room,
        lease: Optional[Lease],
        status: str,
        current_day: int,
        payment: Optional[Payment],
        on_pay_click: Callable[[Room, Lease], None],
        on_whatsapp_click: Callable[[Room, Lease, str], None],
        on_assign_click: Callable[[Room], None],
        on_menu_click: Callable[[Room, Optional[Lease]], None],
        on_view_proof: Optional[Callable[[str], None]] = None,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.room = room
        self.lease = lease
        self.status = status
        self.payment = payment
        self.on_view_proof = on_view_proof
        self.orientation = "vertical"
        self.size_hint_y = None
        self.padding = [dp(16), dp(14), dp(16), dp(14)]
        self.spacing = dp(10)
        self.radius = [dp(14)]
        self.elevation = 2

        # Borde coloreado para identificar inmediatamente el estado
        theme = get_status_theme(status)
        self.line_color = theme["color"]
        self.line_width = dp(2)

        # 1. Cabecera de la tarjeta: Nombre del cuarto y Badge de Estado
        header = MDBoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(40),
            spacing=dp(8)
        )

        title = MDLabel(
            text=room.name,
            bold=True,
            font_style="H6",
            theme_text_color="Primary",
            size_hint_x=0.55
        )
        header.add_widget(title)

        badge = StatusBadge(status=status, day_number=current_day if lease else None)
        header.add_widget(badge)

        # Botón de menú de opciones del cuarto
        menu_btn = MDIconButton(
            icon="dots-vertical",
            size_hint=(None, None),
            size=(dp(36), dp(36)),
            on_release=lambda x: on_menu_click(room, lease)
        )
        header.add_widget(menu_btn)
        self.add_widget(header)

        # 2. Información del Inquilino y Renta
        info_box = MDBoxLayout(
            orientation="vertical",
            size_hint_y=None,
            height=dp(78) if lease else dp(40),
            spacing=dp(2)
        )

        if lease:
            info_box.add_widget(MDLabel(
                text=f"👤 Inquilino: {lease.tenant_name}",
                font_style="Subtitle1",
                bold=True
            ))
            info_box.add_widget(MDLabel(
                text=f"📞 WhatsApp: {lease.tenant_phone}  |  💵 Renta: ${lease.monthly_rent:,.2f}",
                font_style="Body2",
                theme_text_color="Secondary"
            ))
            info_box.add_widget(MDLabel(
                text=f"🔒 Depósito: ${lease.deposit_amount:,.2f}",
                font_style="Caption",
                theme_text_color="Secondary"
            ))
            if payment:
                method_str = f"({payment.payment_method}) " if payment.payment_method else ""
                info_box.add_widget(MDLabel(
                    text=f"✓ Cubierto {method_str}el {payment.paid_date}",
                    font_style="Caption",
                    theme_text_color="Custom",
                    text_color=COLOR_PAGADO,
                    bold=True
                ))
        else:
            info_box.add_widget(MDLabel(
                text=f"💵 Renta sugerida: ${room.default_rent:,.2f} al mes",
                font_style="Subtitle1",
                theme_text_color="Secondary"
            ))
            info_box.add_widget(MDLabel(
                text="Sin contrato activo. Listo para asignación.",
                font_style="Caption",
                theme_text_color="Hint"
            ))

        self.add_widget(info_box)

        # 3. Acciones con botones táctiles grandes (>= 48dp)
        actions_box = MDBoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(52),
            spacing=dp(10)
        )

        if not lease:
            # Cuarto disponible -> Asignar nuevo inquilino
            btn_assign = MDRaisedButton(
                text="➕ ASIGNAR INQUILINO",
                icon="account-plus",
                size_hint=(1, 1),
                md_bg_color=COLOR_DISPONIBLE,
                font_size="16sp",
                on_release=lambda x: on_assign_click(room)
            )
            actions_box.add_widget(btn_assign)
            self.height = dp(175)

        elif status == STATUS_PAGADO:
            if payment and payment.proof_image_path and on_view_proof:
                btn_proof = MDFlatButton(
                    text="📷 COMPROBANTE",
                    size_hint=(0.42, 1),
                    on_release=lambda x: on_view_proof(payment.proof_image_path)
                )
                btn_receipt = MDFillRoundFlatButton(
                    text="💬 WHATSAPP",
                    icon="whatsapp",
                    size_hint=(0.58, 1),
                    md_bg_color=COLOR_PAGADO,
                    text_color=(1, 1, 1, 1),
                    font_size="14sp",
                    on_release=lambda x: on_whatsapp_click(room, lease, status)
                )
                actions_box.add_widget(btn_proof)
                actions_box.add_widget(btn_receipt)
            else:
                btn_receipt = MDFillRoundFlatButton(
                    text="💬 ENVIAR COMPROBANTE WHATSAPP",
                    icon="whatsapp",
                    size_hint=(1, 1),
                    md_bg_color=COLOR_PAGADO,
                    text_color=(1, 1, 1, 1),
                    font_size="15sp",
                    on_release=lambda x: on_whatsapp_click(room, lease, status)
                )
                actions_box.add_widget(btn_receipt)
            self.height = dp(215)

        else:
            # Cuarto PENDIENTE o ATRASADO -> Botón de Pagar y Botón de WhatsApp
            btn_pay = MDRaisedButton(
                text="✓ PAGADO",
                icon="check-bold",
                size_hint=(0.48, 1),
                md_bg_color=COLOR_PAGADO,
                font_size="15sp",
                on_release=lambda x: on_pay_click(room, lease)
            )

            btn_wa = MDFillRoundFlatButton(
                text="💬 COBRAR",
                icon="whatsapp",
                size_hint=(0.52, 1),
                md_bg_color=theme["color"],
                text_color=(1, 1, 1, 1),
                font_size="15sp",
                on_release=lambda x: on_whatsapp_click(room, lease, status)
            )

            actions_box.add_widget(btn_pay)
            actions_box.add_widget(btn_wa)
            self.height = dp(215)

        self.add_widget(actions_box)
