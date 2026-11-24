# 🗺️ Hoja de Ruta del Proyecto (renTalo Roadmap)

> **renTalo** es un juego de palabras (*puzzle word*) que fusiona tres idiomas:
> - 🇫🇮 **talo:** «casa» o «edificio» en finés.
> - 🇬🇧 **rent:** «renta» o «alquiler» en inglés.
> - 🇪🇸 **réntalo:** «¡alquílalo!» en español (*renta + lo*).

Documento oficial para el seguimiento de versiones, funcionalidades y próximos hitos de desarrollo para **renTalo**, la aplicación offline-first para la gestión de cuartos en alquiler.

---

## 📌 Principios de Diseño
1. **100% Offline-First:** Toda la persistencia reside en SQLite local del dispositivo (`rentalo.db`); ningún dato se envía a servidores externos sin el consentimiento expreso del operador.
2. **Español Natural:** Toda la terminología, interfaces, reportes de Excel y plantillas de WhatsApp están diseñadas en lenguaje claro, cordial y comprensible para operadores no técnicos.
3. **Objetivos Táctiles Accesibles:** Botones de al menos 48dp - 52dp y contrastes de color inmediatos (Verde = Pagado, Amarillo = Pendiente días 1-5, Rojo = Atrasado día 6+, Gris = Disponible).
4. **Desacoplamiento Estricto (TDD):** Lógica pura en `core/` (solo biblioteca estándar de Python) y presentación ligera en `ui/` (KivyMD).
5. **Métricas de Calidad:** 53 pruebas unitarias e integrales automatizadas con `pytest` que verifican cada funcionalidad antes de su despliegue.

---

## 🚀 Estado de Hitos (Milestones)

### ✅ Hito 1: Núcleo de Dominio y Persistencia (Completado)
- [x] Modelos de datos: `Room`, `Lease`, `Payment`.
- [x] Base de datos SQLite ([core/database.py](file:///home/razamoraz/Gitprog/rentalo/core/database.py)) con claves foráneas e integridad referencial (`rentalo.db`).
- [x] Idempotencia en confirmación de pagos mensuales (`UNIQUE(lease_id, billing_year, billing_month)`).
- [x] Motor de cobro con ventana de 5 días naturales (`PAGADO`, `PENDIENTE` días 1-5, `ATRASADO` día 6+).
- [x] Exportador CSV con codificación `utf-8-sig` (compatible con acentos en Excel y Sheets).
- [x] Respaldo y restauración transaccional completa en formato JSON.
- [x] Verificación semestral de respaldo vencido (`is_backup_overdue(..., days=180)`).
- [x] 100% cobertura en pruebas unitarias con `pytest` en `tests/`.

### ✅ Hito 2: Interfaz KivyMD y Puente Android (Completado)
- [x] Tarjetas de habitación codificadas por color:
  - 🟢 **Verde (`#2E7D32`):** Pagado al corriente.
  - 🟡 **Amarillo (`#F9A825`):** Pendiente días 1 al 5.
  - 🔴 **Rojo (`#C62828`):** Atrasado a partir del día 6.
  - ⚪ **Gris (`#546E7A`):** Cuarto disponible.
- [x] Banner prominente de advertencia superior cuando el respaldo tiene más de 6 meses.
- [x] Puente de intents Android ([ui/android_bridge.py](file:///home/razamoraz/Gitprog/rentalo/ui/android_bridge.py)) para WhatsApp y Share Intent con fallback a escritorio.
- [x] Diálogos táctiles para nuevo cuarto, asignación de inquilino y registro de pago.

### ✅ Hito 3: Empaquetado Android con Buildozer (Completado)
- [x] Archivo de especificación [buildozer.spec](file:///home/razamoraz/Gitprog/rentalo/buildozer.spec) configurado para API 34 (Android 14) y MinAPI 21 con el paquete `org.rentalo` / nombre `renTalo`.
- [x] Permisos requeridos configurados (`POST_NOTIFICATIONS`, `READ/WRITE_EXTERNAL_STORAGE`, `INTERNET`, `VIBRATE`).

### ✅ Hito 4: CI/CD en GitHub Actions y Notificaciones Locales (Completado)
- [x] Pipeline [.github/workflows/build_apk.yml](file:///home/razamoraz/Gitprog/rentalo/.github/workflows/build_apk.yml) para ejecutar pruebas unitarias bajo Xvfb y compilar el APK automáticamente en cada push a `main` o `master`.
- [x] Publicación del APK descargable como artefacto (`renTalo-Debug-APK`) en GitHub Actions.
- [x] Notificaciones locales mensuales en el dispositivo (días 1 al 5 para cobro, día 6+ para atrasados) con control de no duplicación en `settings`.

### ✅ Hito 4.1: Depósito en Garantía y Cobros Proporcionales (Completado)
- [x] Campo `deposit_amount` en el modelo y base de datos con migración automática.
- [x] Cálculo automático de cobro proporcional por días restantes si el inquilino entra después del día 5 natural.
- [x] Libertad total del operador para editar o mantener el monto del primer mes.
- [x] Plantilla de bienvenida en WhatsApp con desglose inicial (depósito + cobro proporcional + renta futura).
- [x] Desglose de depósito visible en tarjeta de habitación y columna en el reporte CSV.

### ✅ Hito 4.2: Edición y Corrección de Contratos (Completado)
- [x] Función `db.update_lease(...)` para corregir errores de dedo en nombre, teléfono, renta pactada o depósito.
- [x] Diálogo de edición táctil accesible desde el menú contextual (`⋮`) de cada habitación.

### ✅ Hito 4.3: Sincronización e Importación Colaborativa Multi-Supervisor (Completado)
- [x] Función `merge_database_from_json(...)` para combinar datos de otro supervisor sin sobrescribir ni borrar registros existentes.
- [x] Asociación automática de habitaciones, inquilinos e integración de nuevos pagos.
- [x] Botón accesible en el menú de respaldos: *«Combinar datos de otro supervisor (Merge)»*.

### ✅ Hito 4.4: Comprobantes de Pago y Transferencias (Proof of Payment) (Completado)
- [x] Campos `proof_image_path` y `payment_method` (`TRANSFERENCIA` vs `EFECTIVO`) en modelo `Payment` y SQLite con migración automática.
- [x] Almacenamiento local offline de capturas y fotos en subcarpeta segura `comprobantes_pagos/`.
- [x] Botón directo en tarjeta de habitación para consultar el comprobante guardado (`📷 COMPROBANTE`).
- [x] Integración de columna de comprobante y método en exportaciones Excel CSV, respaldos JSON y merge.

---

### ✅ Hito 8: Soporte Multiplataforma Apple (iOS / macOS) (Completado)
- [x] Workflow de GitHub Actions [.github/workflows/build_ios.yml](file:///home/razamoraz/Gitprog/rentalo/.github/workflows/build_ios.yml) con runner `macos-14` (Apple Silicon M1/M2) para compilar la app con `kivy-ios`.
- [x] Adaptación en [ui/android_bridge.py](file:///home/razamoraz/Gitprog/rentalo/ui/android_bridge.py) para apertura de WhatsApp mediante esquema nativo `whatsapp://send` y almacenamiento accesible en `~/Documents`.
- [x] Pruebas unitarias de compatibilidad iOS en `tests/test_android_bridge.py`.

---

## 🔮 Próximos Hitos en Desarrollo

### 🔲 Hito 6: Recibo de Finiquito y Entrega de Habitación por WhatsApp (Prioridad 1)
- [ ] Al finalizar un contrato, calculadora interactiva de deducciones de depósito (daños, pintura, llaves extraviadas, aseo profundo).
- [ ] Cálculo en tiempo real de saldo a favor del inquilino (devolución) o saldo pendiente a favor del arrendador.
- [ ] Generación automática de comprobante formal de finiquito y entrega-recepción formal vía WhatsApp.
- [ ] Botón de envío del *Reglamento Interno de la Casa* en 1 toque.

### 🔲 Hito 5: Captura y Almacenamiento Local de Identificación (INE / ID) (Prioridad 2)
- [ ] Captura de foto frontal y trasera de INE mediante cámara o selector de galería del teléfono.
- [ ] Compresión local offline (JPEG optimizado) en carpeta privada de la aplicación (`fotos_inquilinos/`).
- [ ] Visor emergente dentro de la app para consultar la identificación del inquilino en cualquier momento sin internet.
- [ ] Vinculación directa en la ficha y contrato del inquilino.

### 🚫 Hito 7: Calculadora y División de Servicios Compartidos (Descartado)
- *Descartado según requerimiento del proyecto: Todos los servicios (luz, agua, gas, internet) están incluidos en la renta mensual.*
