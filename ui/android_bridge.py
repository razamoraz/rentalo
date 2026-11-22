import os
import re
import urllib.parse
import webbrowser
from pathlib import Path
from typing import Dict, Any


def save_payment_proof(source_path: str, lease_id: int, year: int, month: int) -> str:
    """
    Guarda y organiza localmente la captura de pantalla o foto de comprobante de pago.
    Almacena el archivo en la subcarpeta 'comprobantes_pagos/' y retorna la ruta relativa.
    """
    import shutil
    src = Path(source_path)
    if not src.exists():
        raise FileNotFoundError(f"El archivo fuente no existe: {source_path}")

    ext = src.suffix.lower() or ".jpg"
    dest_dir = Path("comprobantes_pagos")
    dest_dir.mkdir(parents=True, exist_ok=True)

    dest_filename = f"pago_{lease_id}_{year}_{month:02d}{ext}"
    dest_path = dest_dir / dest_filename
    shutil.copy2(src, dest_path)

    return str(dest_path)


def view_image_file(image_path: str) -> bool:
    """
    Abre el visor de imágenes nativo de Android o del sistema de escritorio.
    """
    path_obj = Path(image_path)
    if not path_obj.exists():
        return False

    try:
        from kivy.utils import platform
        if platform == "android":
            from jnius import autoclass, cast  # type: ignore
            Intent = autoclass("android.content.Intent")
            Uri = autoclass("android.net.Uri")
            File = autoclass("java.io.File")
            PythonActivity = autoclass("org.kivy.android.PythonActivity")

            intent = Intent(Intent.ACTION_VIEW)
            file_java = File(str(path_obj.resolve()))
            uri = Uri.fromFile(file_java)
            intent.setDataAndType(uri, "image/*")
            intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)

            PythonActivity.mActivity.startActivity(intent)
            return True
    except Exception:
        pass

    try:
        webbrowser.open(f"file://{path_obj.resolve()}")
        return True
    except Exception:
        return False


def clean_phone_for_whatsapp(phone: str) -> str:
    """
    Normaliza el número de teléfono para WhatsApp:
    - Elimina caracteres no numéricos (+, espacios, guiones, paréntesis).
    - Si tiene 10 dígitos (número local mexicano común), añade el código de país '521'.
    - Si ya tiene código de país (12 o 13 dígitos), lo preserva.
    """
    digits = re.sub(r"\D", "", phone)
    if len(digits) == 10:
        return f"521{digits}"
    return digits


def get_export_directory() -> Path:
    """
    Determina y asegura la existencia del directorio donde se guardarán los respaldos y CSVs.
    En Android busca almacenamiento externo accesible; en escritorio usa una carpeta de usuario.
    """
    # Intentar obtener ruta de almacenamiento externo en Android
    export_dir: Path
    try:
        from kivy.utils import platform
        if platform == "android":
            from android.storage import primary_external_storage_path  # type: ignore
            base = primary_external_storage_path()
            export_dir = Path(base) / "Download" / "renTalo"
        elif platform == "ios":
            export_dir = Path.home() / "Documents"
        else:
            export_dir = Path.home() / "renTalo_Respaldos"
    except Exception:
        export_dir = Path.home() / "renTalo_Respaldos"

    try:
        export_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        # Respaldo si no hay permisos en la ruta preferida
        export_dir = Path("exportaciones_rentalo")
        export_dir.mkdir(parents=True, exist_ok=True)

    return export_dir


def open_whatsapp(phone: str, message: str) -> bool:
    """
    Abre la aplicación WhatsApp con el mensaje prellenado.
    Prioriza el intent nativo de Android y recurre a webbrowser como fallback.
    """
    clean_phone = clean_phone_for_whatsapp(phone)
    encoded_message = urllib.parse.quote(message)
    whatsapp_url = f"https://wa.me/{clean_phone}?text={encoded_message}"

    # Intento 1: Intent nativo en Android mediante PyJNIus
    try:
        from kivy.utils import platform
        if platform == "android":
            from jnius import autoclass  # type: ignore
            Intent = autoclass("android.content.Intent")
            Uri = autoclass("android.net.Uri")
            PythonActivity = autoclass("org.kivy.android.PythonActivity")

            intent = Intent(Intent.ACTION_VIEW)
            intent.setData(Uri.parse(whatsapp_url))
            PythonActivity.mActivity.startActivity(intent)
            return True
        elif platform == "ios":
            # En iOS el esquema directo whatsapp:// abre la app instalada
            ios_url = f"whatsapp://send?phone={clean_phone}&text={encoded_message}"
            if webbrowser.open(ios_url):
                return True
    except Exception:
        pass

    # Intento 2: Usar plyer si está soportado
    try:
        from plyer import unique_open  # type: ignore
        unique_open(whatsapp_url)
        return True
    except Exception:
        pass

    # Fallback general para escritorio y emulador
    try:
        webbrowser.open(whatsapp_url)
        return True
    except Exception:
        return False


def send_local_notification(title: str, message: str) -> bool:
    """
    Envía una notificación local en el dispositivo Android mediante plyer o PyJNIus.
    En entorno de escritorio o pruebas retorna True de forma segura.
    """
    # Intento 1: Plyer notification
    try:
        from plyer import notification  # type: ignore
        notification.notify(
            title=title,
            message=message,
            app_name="renTalo",
            ticker="renTalo",
            timeout=10
        )
        return True
    except Exception:
        pass

    # Intento 2: Android PyJNIus con NotificationManager y canal en Android 8+
    try:
        from kivy.utils import platform
        if platform == "android":
            from jnius import autoclass  # type: ignore
            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            Context = autoclass("android.content.Context")
            NotificationManager = autoclass("android.app.NotificationManager")
            NotificationChannel = autoclass("android.app.NotificationChannel")
            NotificationBuilder = autoclass("android.app.Notification$Builder")

            context = PythonActivity.mActivity
            notif_service = context.getSystemService(Context.NOTIFICATION_SERVICE)

            channel_id = "rentalo_recordatorios"
            channel_name = "Recordatorios de Renta"
            importance = NotificationManager.IMPORTANCE_DEFAULT

            channel = NotificationChannel(channel_id, channel_name, importance)
            notif_service.createNotificationChannel(channel)

            builder = NotificationBuilder(context, channel_id)
            builder.setContentTitle(title)
            builder.setContentText(message)
            builder.setSmallIcon(context.getApplicationInfo().icon)
            builder.setAutoCancel(True)

            notif_service.notify(1001, builder.build())
            return True
    except Exception:
        pass

    # Fallback para escritorio / pruebas
    return True


def share_file(file_path: str, mime_type: str = "text/plain", title: str = "Compartir respaldo") -> Dict[str, Any]:
    """
    Comparte un archivo (CSV o JSON) usando el selector de Android (Share Intent) o plyer.
    En escritorio confirma la ruta donde quedó guardado.
    """
    path_obj = Path(file_path)
    if not path_obj.exists():
        return {"success": False, "error": f"El archivo {file_path} no existe."}

    # Intentar con plyer.share
    try:
        from plyer import share  # type: ignore
        share.share_file(file_path)
        return {"success": True, "path": file_path, "method": "plyer.share"}
    except Exception:
        pass

    # Intentar con intent nativo de Android
    try:
        from kivy.utils import platform
        if platform == "android":
            from jnius import autoclass, cast  # type: ignore
            Intent = autoclass("android.content.Intent")
            Uri = autoclass("android.net.Uri")
            File = autoclass("java.io.File")
            PythonActivity = autoclass("org.kivy.android.PythonActivity")

            share_intent = Intent(Intent.ACTION_SEND)
            share_intent.setType(mime_type)

            file_java = File(file_path)
            uri = Uri.fromFile(file_java)
            share_intent.putExtra(Intent.EXTRA_STREAM, cast("android.os.Parcelable", uri))

            chooser = Intent.createChooser(share_intent, title)
            PythonActivity.mActivity.startActivity(chooser)
            return {"success": True, "path": file_path, "method": "android.intent"}
    except Exception:
        pass

    # Fallback en escritorio
    return {"success": True, "path": file_path, "method": "desktop"}

