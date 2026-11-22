from typing import Dict, Any, Tuple
from core.billing_engine import (
    STATUS_PAGADO,
    STATUS_PENDIENTE,
    STATUS_ATRASADO
)

STATUS_DISPONIBLE = "DISPONIBLE"

# Paleta de colores de alto contraste para visibilidad en exteriores y pantallas móviles
# Formato RGBA (0.0 a 1.0) para Kivy / KivyMD
COLOR_PAGADO: Tuple[float, float, float, float] = (0.18, 0.49, 0.20, 1.0)       # Verde #2E7D32
COLOR_PENDIENTE: Tuple[float, float, float, float] = (0.97, 0.65, 0.09, 1.0)    # Amarillo Ámbar #F9A825
COLOR_ATRASADO: Tuple[float, float, float, float] = (0.78, 0.16, 0.16, 1.0)     # Rojo Carmesí #C62828
COLOR_DISPONIBLE: Tuple[float, float, float, float] = (0.37, 0.49, 0.54, 1.0)   # Gris Pizarra #546E7A
COLOR_BANNER_WARNING: Tuple[float, float, float, float] = (0.84, 0.18, 0.14, 1.0) # Rojo Alerta #D32F2F

# Dimensiones táctiles mínimas para botones accesibles (para operadores no técnicos)
MIN_TOUCH_HEIGHT = "48dp"
BUTTON_HEIGHT = "52dp"
CARD_PADDING = "16dp"


def get_status_theme(status: str) -> Dict[str, Any]:
    """
    Retorna la configuración visual (color, etiqueta e icono) según el estado del cuarto.
    """
    if status == STATUS_PAGADO:
        return {
            "color": COLOR_PAGADO,
            "label": "PAGADO",
            "icon": "check-circle",
            "description": "Renta al corriente para este mes."
        }
    elif status == STATUS_PENDIENTE:
        return {
            "color": COLOR_PENDIENTE,
            "label": "PENDIENTE",
            "icon": "clock-alert-outline",
            "description": "Dentro de la ventana regular de los primeros 5 días."
        }
    elif status == STATUS_ATRASADO:
        return {
            "color": COLOR_ATRASADO,
            "label": "ATRASADO",
            "icon": "alert-circle",
            "description": "Han pasado más de 5 días naturales sin registrar pago."
        }
    else:
        return {
            "color": COLOR_DISPONIBLE,
            "label": "DISPONIBLE",
            "icon": "home-outline",
            "description": "Cuarto disponible para nuevo inquilino."
        }

