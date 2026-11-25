import os
import re
import shutil
import tempfile
import urllib.parse
import webbrowser
from pathlib import Path
from typing import Dict, Any, Optional, Callable


def get_media_directory(subfolder: str) -> Path:
    """
    Retorna un directorio escribible y persistente para archivos multimedia locales
    (comprobantes_pagos, fotos_inquilinos) compatible con Android, iOS y escritorio.
    """
    try:
        from kivy.utils import platform
        if platform == "ios":
            base = Path.home() / "Documents" / "renTalo_Media"
            dest = base / subfolder
            dest.mkdir(parents=True, exist_ok=True)
            return dest
        elif platform == "android":
            from android.storage import app_storage_path  # type: ignore
            base = Path(app_storage_path())
            dest = base / subfolder
            dest.mkdir(parents=True, exist_ok=True)
            return dest
    except Exception:
        pass

    dest = Path(subfolder)
    dest.mkdir(parents=True, exist_ok=True)
    return dest


def save_compressed_image(
    source_path: str,
    subfolder: str,
    filename_stem: str,
    max_dimension: int = 1280,
    quality: int = 80
) -> str:
    """
    Optimiza y guarda una imagen localmente en formato JPEG comprimido offline usando Pillow.
    Si Pillow falla o el archivo no es una imagen decodificable, realiza copia directa segura.
    """
    src = Path(source_path)
    if not src.exists():
        raise FileNotFoundError(f"El archivo fuente no existe: {source_path}")

    dest_dir = get_media_directory(subfolder)

    try:
        from PIL import Image, ImageOps
        dest_path = dest_dir / f"{filename_stem}.jpg"
        with Image.open(src) as img:
            img = ImageOps.exif_transpose(img)
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")
            elif img.mode == "L":
                img = img.convert("RGB")
            img.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)
            img.save(dest_path, format="JPEG", quality=quality, optimize=True)
        return str(dest_path)
    except Exception:
        ext = src.suffix.lower() or ".jpg"
        dest_path = dest_dir / f"{filename_stem}{ext}"
        shutil.copy2(src, dest_path)
        return str(dest_path)


def save_payment_proof(source_path: str, lease_id: int, year: int, month: int) -> str:
    """
    Guarda y optimiza localmente la captura de pantalla o foto de comprobante de pago
    en la carpeta 'comprobantes_pagos/'.
    """
    return save_compressed_image(
        source_path=source_path,
        subfolder="comprobantes_pagos",
        filename_stem=f"pago_{lease_id}_{year}_{month:02d}"
    )


def save_tenant_id_photo(source_path: str, lease_id: int, side: str) -> str:
    """
    Guarda y comprime localmente la foto frontal o trasera de la INE / identificación
    en la carpeta privada 'fotos_inquilinos/'.
    """
    side_clean = "frente" if side.lower() in ("front", "frente") else "reverso"
    return save_compressed_image(
        source_path=source_path,
        subfolder="fotos_inquilinos",
        filename_stem=f"ine_contrato_{lease_id}_{side_clean}"
    )


def pick_image_file(on_selected: Callable[[Optional[str]], None]) -> bool:
    """
    Abre el selector nativo de galería/archivos (Android/iOS/escritorio) para elegir una imagen.
    Invoca on_selected(ruta) o on_selected(None) si se cancela.
    """
    return _pick_file(
        on_selected=on_selected,
        title="Seleccionar imagen",
        plyer_filters=[["Imágenes", "*.png", "*.jpg", "*.jpeg", "*.webp"]],
        tk_filetypes=[("Imágenes", "*.png *.jpg *.jpeg *.webp"), ("Todos", "*.*")]
    )


def pick_json_file(on_selected: Callable[[Optional[str]], None]) -> bool:
    """
    Abre el selector nativo de archivos para elegir un archivo .json de respaldo.
    Invoca on_selected(ruta) o on_selected(None) si se cancela.
    """
    return _pick_file(
        on_selected=on_selected,
        title="Seleccionar archivo de respaldo (.json)",
        plyer_filters=[["Respaldos JSON", "*.json"]],
        tk_filetypes=[("Archivos JSON", "*.json"), ("Todos", "*.*")]
    )


def _pick_file(
    on_selected: Callable[[Optional[str]], None],
    title: str,
    plyer_filters: list,
    tk_filetypes: list
) -> bool:
    """Implementación interna del selector de archivos con fallbacks."""
    try:
        from plyer import filechooser  # type: ignore

        def _handle(selection):
            if selection and len(selection) > 0 and Path(selection[0]).exists():
                on_selected(str(selection[0]))
            else:
                on_selected(None)

        filechooser.open_file(
            title=title,
            filters=plyer_filters,
            on_selection=_handle
        )
        return True
    except Exception:
        pass

    # Fallback escritorio con tkinter si está disponible
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        selected = filedialog.askopenfilename(
            title=title,
            filetypes=tk_filetypes
        )
        root.destroy()
        on_selected(selected if selected else None)
        return bool(selected)
    except Exception:
        on_selected(None)
        return False


def capture_camera_photo(on_captured: Callable[[Optional[str]], None], filename_prefix: str = "captura") -> bool:
    """
    Lanza la cámara nativa del dispositivo mediante plyer.camera y guarda la foto temporalmente
    para ser comprimida. En escritorio sin cámara soportada retorna False de forma segura.
    """
    try:
        from plyer import camera  # type: ignore
        tmp_dir = Path(tempfile.gettempdir())
        target = tmp_dir / f"{filename_prefix}.jpg"

        def _done(filepath):
            if filepath and Path(filepath).exists():
                on_captured(str(filepath))
            else:
                on_captured(None)

        camera.take_picture(filename=str(target), on_complete=_done)
        return True
    except Exception:
        on_captured(None)
        return False


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

