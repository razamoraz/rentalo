# RentaFácil 🏠📱

Aplicación Android ultra-simple y 100% offline en español para la gestión mensual de renta de cuartos por parte de operadores no técnicos.

---

## 🎨 Características de Milestone 2 (Interfaz KivyMD & Android)

1. **Separación Arquitectónica Estricta:**
   - `core/`: 100% biblioteca estándar de Python (`sqlite3`, `dataclasses`, `datetime`, `csv`, `json`, `urllib.parse`, `pathlib`). Sin dependencias de UI para pruebas unitarias instantáneas y robustas.
   - `ui/`: Capa de presentación KivyMD con objetivos táctiles grandes (mínimo 48-52dp de alto) y tipografía legible de alto contraste.
   - `ui/android_bridge.py`: Gestión de intents de Android (WhatsApp y Share Intent) con fallback transparente para desarrollo en escritorio.

2. **Tarjetas de Cuartos Codificadas por Color:**
   - 🟢 **Verde (`#2E7D32`) - PAGADO:** El inquilino está al corriente este mes. Botón grande de 1 toque para enviar comprobante de pago por WhatsApp.
   - 🟡 **Amarillo (`#F9A825`) - PENDIENTE (Días 1-5):** Dentro de la ventana regular de los primeros 5 días naturales del mes. Botón de cobro cordial por WhatsApp y botón de confirmación de pago.
   - 🔴 **Rojo (`#C62828`) - ATRASADO (Día 6+):** Pasaron los 5 días de gracia. Botón de recordatorio urgente por WhatsApp y botón para registrar pago.
   - ⚪ **Gris Pizarra (`#546E7A`) - DISPONIBLE:** Cuarto desocupado. Botón grande `+ ASIGNAR INQUILINO`.

3. **Depósito en Garantía y Cobros Proporcionales (Milestone 4.1):**
   - **Depósito en garantía:** Registrado en cada contrato (`deposit_amount`), visible en la tarjeta del cuarto, respaldado en JSON y desglosado en el CSV.
   - **Cobro proporcional por días restantes:** Si un inquilino entra después del día 5 natural, la app calcula y sugiere el cobro proporcional exacto según los días restantes del mes, con total libertad para que el operador lo ajuste manualmente o cobre mes completo.
   - **Mensaje de bienvenida por WhatsApp:** Envía el desglose inicial (depósito + cobro proporcional del primer mes + renta regular futura).

4. **Sincronización Multi-Supervisor, Edición y Comprobantes de Transferencia (Milestones 4.2 - 4.4):**
   - **Edición de contratos:** Corrección inmediata de errores tipográficos en nombre del inquilino, teléfono WhatsApp, renta acordada o monto del depósito.
   - **Combinación segura de respaldos (Merge):** Permite que varios supervisores compartan archivos `.json` e integren cuartos, contratos y pagos sin borrar ni duplicar datos existentes.
   - **Comprobantes de transferencia bancaria:** Posibilidad opcional de vincular capturas de pantalla de transferencia bancaria (SPEI/BBVA/etc.) o fotos de recibos a cada pago, almacenados de forma local offline en `comprobantes_pagos/` y consultables con un toque.

5. **Banner Prominente de Respaldo Semestral:**
   - Cuando `is_backup_overdue()` es `True` (más de 180 días sin respaldar o primera vez), se muestra una alerta roja/ámbar en la parte superior con un botón directo `RESPALDAR AHORA MISMO`.
   - Permite exportar a Excel (`.csv` con codificación `utf-8-sig`) y crear respaldos completos portátiles (`.json`).

4. **Notificaciones Locales de Recordatorio Mensual:**
   - Días 1 al 5: Alerta local cordial indicando el inicio del período de cobro y cuántos cuartos están pendientes.
   - Día 6 en adelante: Alerta local de aviso si existen cuartos con pagos atrasados.
   - Idempotencia: Registra el envío en la base de datos para no saturar al usuario con avisos repetitivos en el mismo mes.

---

## 🤖 CI/CD Automatizado con GitHub Actions

El archivo `.github/workflows/build_apk.yml` automatiza:
1. Ejecución de las 40 pruebas unitarias en `ubuntu-latest`.
2. Compilación del APK debug de Android con `buildozer` en `ubuntu-22.04` (JDK 17 + Python 3.11).
3. Publicación del artefacto APK descargable en GitHub Actions en cada `push` a las ramas `main` y `master`.

---

## 🗺️ Hoja de Ruta y Próximos Hitos

Consulta [ROADMAP.md](file:///home/razamoraz/Gitprog/rentalo/ROADMAP.md) para conocer el desglose detallado de los hitos completados y los que se encuentran en desarrollo (fotos de INE offline, finiquitos de depósito y división de recibos CFE).

---

## 🧪 Pruebas Unitarias TDD

Para correr la suite de pruebas completa:

```bash
.venv/bin/pytest -v tests/
```

Todas las 35 pruebas cubren:
- Operaciones CRUD y claves foráneas en SQLite.
- Idempotencia de pagos por mes/año.
- Cálculo de la ventana de pago (Día 1, Día 5, Día 6).
- Generación de links de WhatsApp en español con codificación URL.
- Exportación e importación transaccional JSON con rollback ante fallos.
- Lógica de detección de respaldos vencidos (180 días).
- Inicialización y renderizado de la UI de KivyMD.

---

## 🚀 Ejecución en Escritorio

```bash
.venv/bin/python main.py
```

---

## 📦 Compilación para Android (APK con Buildozer)

```bash
buildozer android debug
```

