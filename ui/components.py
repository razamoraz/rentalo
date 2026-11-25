from typing import Optional, Callable, Tuple
from kivy.metrics import dp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.card import MDCard
from kivymd.uix.label import MDLabel, MDIcon
from kivymd.uix.button import (
    MDRaisedButton,
    MDFillRoundFlatIconButton,
    MDRectangleFlatIconButton,
    MDIconButton
)

from core.models import Room, Lease, Payment
from core.billing_engine import (
    STATUS_PAGADO,
    STATUS_PENDIENTE,
    STATUS_ATRASADO
)
from ui.theme_config import (
    COLOR_PAGADO,
    COLOR_DISPONIBLE,
    COLOR_BANNER_WARNING,
    STATUS_DISPONIBLE,
    get_status_theme
)


def _make_icon_row(
    icon_name: str,
    text: str,
    font_style: str = "Body2",
    bold: bool = False,
    theme_text_color: str = "Secondary",
    text_color: Optional[Tuple[float, float, float, float]] = None,
    icon_color: Optional[Tuple[float, float, float, float]] = None
) -> MDBoxLayout:
    """Crea una fila limpia con icono Material Design y etiqueta adaptable (sin emojis tofu)."""
    row = MDBoxLayout(
        orientation="horizontal",
        size_hint_y=None,
        adaptive_height=True,
        spacing=dp(8)
    )
    resolved_icon_color = icon_color or text_color or (0.35, 0.35, 0.35, 1.0)
    icon = MDIcon(
        icon=icon_name,
        theme_text_color="Custom",
        text_color=resolved_icon_color,
        font_size=dp(18),
        size_hint=(None, None),
        size=(dp(20), dp(22)),
        pos_hint={"center_y": 0.5}
    )
    label_kwargs = {
        "text": text,
        "font_style": font_style,
        "bold": bold,
        "adaptive_height": True,
        "theme_text_color": "Custom" if text_color else theme_text_color,
    }
    if text_color:
        label_kwargs["text_color"] = text_color
    label = MDLabel(**label_kwargs)
    row.add_widget(icon)
    row.add_widget(label)
    return row


class BackupWarningBanner(MDCard):
    """
    Banner de advertencia prominente que se muestra en la parte superior cuando
    han transcurrido 6 meses (180 días) sin realizar un respaldo de la base de datos.
    """
    def __init__(self, on_backup_click: Callable[[], None], **kwargs):
        super().__init__(**kwargs)
        self.orientation = "vertical"
        self.size_hint_y = None
        self.adaptive_height = True
        self.padding = [dp(16), dp(14), dp(16), dp(14)]
        self.spacing = dp(10)
        self.radius = [dp(12)]
        self.elevation = 3
        self.md_bg_color = COLOR_BANNER_WARNING

        msg_layout = MDBoxLayout(
            orientation="horizontal",
            spacing=dp(10),
            size_hint_y=None,
            adaptive_height=True
        )

        icon = MDIcon(
            icon="alert-octagon",
            theme_text_color="Custom",
            text_color=(1, 1, 1, 1),
            font_size=dp(28),
            size_hint=(None, None),
            size=(dp(32), dp(32)),
            pos_hint={"center_y": 0.5}
        )

        label = MDLabel(
            text="ALERTA DE SEGURIDAD\nHace más de 6 meses no realiza un respaldo.",
            theme_text_color="Custom",
            text_color=(1, 1, 1, 1),
            bold=True,
            font_style="Subtitle2",
            adaptive_height=True
        )

        msg_layout.add_widget(icon)
        msg_layout.add_widget(label)
        self.add_widget(msg_layout)

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
    Insignia de estado de una sola línea con icono, contraste accesible y ancho adaptable.
    """
    def __init__(self, status: str, day_number: Optional[int] = None, **kwargs):
        super().__init__(**kwargs)
        self.orientation = "horizontal"
        self.size_hint = (None, None)
        self.height = dp(30)
        self.padding = [dp(10), dp(4), dp(12), dp(4)]
        self.spacing = dp(5)
        self.radius = [dp(15)]

        theme = get_status_theme(status)
        self.md_bg_color = theme["color"]
        badge_text_color = theme["text_color"]

        icon = MDIcon(
            icon=theme["icon"],
            theme_text_color="Custom",
            text_color=badge_text_color,
            font_size=dp(16),
            size_hint=(None, None),
            size=(dp(18), dp(18)),
            pos_hint={"center_y": 0.5}
        )
        self.add_widget(icon)

        label_text = theme["label"]
        if status == STATUS_PENDIENTE and day_number is not None:
            label_text = f"PENDIENTE · Día {day_number}/5"
        elif status == STATUS_ATRASADO and day_number is not None:
            label_text = f"ATRASADO · Día {day_number}"

        text = MDLabel(
            text=label_text,
            theme_text_color="Custom",
            text_color=badge_text_color,
            bold=True,
            font_style="Caption",
            adaptive_size=True,
            pos_hint={"center_y": 0.5},
            shorten=False
        )

        def _update_width(instance, value):
            text_w = value[0]
            if text_w > 0:
                self.width = dp(10) + dp(18) + dp(5) + text_w + dp(12)

        text.bind(texture_size=_update_width)
        self.add_widget(text)

        # Ancho inicial estimado previo al primer layout
        self.width = dp(46) + (len(label_text) * dp(7))


class RoomCard(MDCard):
    """
    Tarjeta de habitación codificada por color con altura adaptable, iconografía Material Design
    y botones táctiles amplios (mínimo 48dp) para uso móvil cómodo.
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
        self.adaptive_height = True
        self.padding = [dp(14), dp(12), dp(14), dp(14)]
        self.spacing = dp(10)
        self.radius = [dp(14)]
        self.elevation = 2

        theme = get_status_theme(status)
        self.line_color = theme["color"]
        self.line_width = dp(2)

        # 1. Cabecera: Nombre del cuarto + Badge + Menú
        header = MDBoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            adaptive_height=True,
            spacing=dp(6)
        )

        title = MDLabel(
            text=room.name,
            bold=True,
            font_style="Subtitle1",
            theme_text_color="Primary",
            adaptive_height=True,
            pos_hint={"center_y": 0.5}
        )
        header.add_widget(title)

        badge = StatusBadge(
            status=status,
            day_number=current_day if lease else None,
            pos_hint={"center_y": 0.5}
        )
        header.add_widget(badge)

        menu_btn = MDIconButton(
            icon="dots-vertical",
            size_hint=(None, None),
            size=(dp(36), dp(36)),
            pos_hint={"center_y": 0.5},
            on_release=lambda x: on_menu_click(room, lease)
        )
        header.add_widget(menu_btn)
        self.add_widget(header)

        # 2. Información del inquilino o estado disponible (altura dinámica sin traslapes)
        info_box = MDBoxLayout(
            orientation="vertical",
            size_hint_y=None,
            adaptive_height=True,
            spacing=dp(4)
        )

        if lease:
            info_box.add_widget(_make_icon_row(
                icon_name="account",
                text=lease.tenant_name,
                font_style="Subtitle1",
                bold=True,
                theme_text_color="Primary",
                icon_color=(0.15, 0.35, 0.35, 1.0)
            ))
            info_box.add_widget(_make_icon_row(
                icon_name="phone",
                text=f"WhatsApp: {lease.tenant_phone}  |  Renta: ${lease.monthly_rent:,.2f}",
                font_style="Body2",
                theme_text_color="Secondary"
            ))

            has_id = bool(lease.id_front_path or lease.id_back_path)
            dep_text = f"Depósito: ${lease.deposit_amount:,.2f}"
            if has_id:
                dep_text += "  |  INE registrada"
            info_box.add_widget(_make_icon_row(
                icon_name="card-account-details-outline" if has_id else "shield-lock-outline",
                text=dep_text,
                font_style="Caption",
                theme_text_color="Secondary"
            ))

            if payment:
                method_str = f"({payment.payment_method}) " if payment.payment_method else ""
                info_box.add_widget(_make_icon_row(
                    icon_name="check-circle-outline",
                    text=f"Cubierto {method_str}el {payment.paid_date}",
                    font_style="Caption",
                    bold=True,
                    text_color=COLOR_PAGADO,
                    icon_color=COLOR_PAGADO
                ))
        else:
            info_box.add_widget(_make_icon_row(
                icon_name="cash",
                text=f"Renta sugerida: ${room.default_rent:,.2f} / mes",
                font_style="Subtitle2",
                theme_text_color="Secondary"
            ))
            info_box.add_widget(MDLabel(
                text="Sin contrato activo. Listo para asignación.",
                font_style="Caption",
                theme_text_color="Hint",
                adaptive_height=True
            ))

        self.add_widget(info_box)

        # 3. Botones de acción (>= 48dp de alto con iconos Material Design reales)
        actions_box = MDBoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(48),
            spacing=dp(8)
        )

        if not lease:
            btn_assign = MDFillRoundFlatIconButton(
                text="ASIGNAR INQUILINO",
                icon="account-plus",
                size_hint=(1, 1),
                md_bg_color=COLOR_DISPONIBLE,
                text_color=(1, 1, 1, 1),
                icon_color=(1, 1, 1, 1),
                font_size="15sp",
                on_release=lambda x: on_assign_click(room)
            )
            actions_box.add_widget(btn_assign)

        elif status == STATUS_PAGADO:
            if payment and payment.proof_image_path and on_view_proof:
                btn_proof = MDRectangleFlatIconButton(
                    text="COMPROBANTE",
                    icon="image-outline",
                    size_hint=(0.46, 1),
                    on_release=lambda x: on_view_proof(payment.proof_image_path)
                )
                btn_receipt = MDFillRoundFlatIconButton(
                    text="WHATSAPP",
                    icon="whatsapp",
                    size_hint=(0.54, 1),
                    md_bg_color=COLOR_PAGADO,
                    text_color=(1, 1, 1, 1),
                    icon_color=(1, 1, 1, 1),
                    font_size="14sp",
                    on_release=lambda x: on_whatsapp_click(room, lease, status)
                )
                actions_box.add_widget(btn_proof)
                actions_box.add_widget(btn_receipt)
            else:
                btn_receipt = MDFillRoundFlatIconButton(
                    text="ENVIAR COMPROBANTE",
                    icon="whatsapp",
                    size_hint=(1, 1),
                    md_bg_color=COLOR_PAGADO,
                    text_color=(1, 1, 1, 1),
                    icon_color=(1, 1, 1, 1),
                    font_size="15sp",
                    on_release=lambda x: on_whatsapp_click(room, lease, status)
                )
                actions_box.add_widget(btn_receipt)

        else:
            btn_pay = MDFillRoundFlatIconButton(
                text="PAGADO",
                icon="check-bold",
                size_hint=(0.48, 1),
                md_bg_color=COLOR_PAGADO,
                text_color=(1, 1, 1, 1),
                icon_color=(1, 1, 1, 1),
                font_size="15sp",
                on_release=lambda x: on_pay_click(room, lease)
            )

            btn_wa = MDFillRoundFlatIconButton(
                text="COBRAR",
                icon="whatsapp",
                size_hint=(0.52, 1),
                md_bg_color=theme["color"],
                text_color=theme["text_color"],
                icon_color=theme["text_color"],
                font_size="15sp",
                on_release=lambda x: on_whatsapp_click(room, lease, status)
            )

            actions_box.add_widget(btn_pay)
            actions_box.add_widget(btn_wa)

        self.add_widget(actions_box)
