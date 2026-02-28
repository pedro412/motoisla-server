# Plan Maestro Status

Referencia: `plan-maestro-v1.md` (v1)

## Resumen ejecutivo
- Avance general estimado: **94-96% del backend v1**.
- Fases cerradas: **0, 1, 2, 3, 4, 5, 6, 7, 8**.
- Fases pendientes: **ninguna de backend core**.

## Estado por fase

### Fase 0 — Base técnica
Estado: ✅ Cerrada
- Apps modulares creadas.
- API versionada en `/api/v1/`.
- Docker + Makefile operativos.

### Fase 1 — Accounts + Roles + Auth
Estado: ✅ Cerrada
- Usuario custom.
- Seed de roles (`ADMIN`, `CASHIER`, `INVESTOR`).
- JWT funcionando.

### Fase 2 — Catálogo + Inventario
Estado: ✅ Cerrada
- CRUD de productos/imágenes.
- Movimientos de inventario y stock agregado.
- Constraints críticos (SKU único, no stock negativo por salida).

### Fase 3 — Compras/Recepciones + Imports
Estado: ✅ Cerrada
- Import batch parseable y editable por línea.
- Confirmación con validaciones de consistencia.
- Recepción e impacto de inventario idempotentes.

### Fase 4 — POS Ventas
Estado: ✅ Cerrada (core)
- Venta + líneas + pagos.
- Confirmación idempotente.
- Anulación con ventana para cajero y mayor alcance para admin.
- Descuento >10% requiere override admin.
- Iteración operativa reciente:
  - catálogo de planes de comisión de tarjeta configurable.
  - snapshot de comisión por pago para utilidad/ledger histórico.
  - `GET /sales/` enriquecido para historial UI (`cashier_username`, `void_reason`, `can_void`).

### Fase 5 — Apartados y Saldo a Favor
Estado: ✅ Cerrada
- Reserva inventario en apartado.
- Liquidación con validación de saldo exacto.
- Expiración con crédito a favor y liberación de inventario.
- Aplicación de crédito vía endpoint.

### Fase 6 — Inversionistas + Ledger
Estado: ✅ Cerrada (núcleo)
- Endpoints admin para depósito/retiro/reinversión.
- Endpoints de consulta propia para inversionista.
- Asignaciones de producto a inversionista.
- Invariantes de capital/profit aplicadas en operaciones manuales.
- Iteración operativa adicional:
  - alta de inversionista sin usuario obligatorio con capital inicial opcional
  - balances agregados en `GET /investors/` y `GET /investors/{id}/`
  - compra transaccional en `POST /investors/{id}/purchases/`
  - `GET /investors/{id}/ledger/` con paginación estándar
  - `investor_assignable_qty` expuesto en productos para bloquear asignaciones duplicadas

### Fase 7 — Auditoría + Métricas base
Estado: ✅ Cerrada (scope backend)
Completado:
- Audit log de acciones críticas.
- Métricas ampliadas en `/api/v1/metrics/`:
  - rango de fechas (`date_from`, `date_to`)
  - ticket promedio y total por rango
  - top productos por unidades e importe neto
  - desglose por método de pago y tipo de tarjeta
- Endpoint de reporte admin readonly: `/api/v1/reports/sales/` con:
  - agregación diaria (`sales_by_day`)
  - agregación por cajero (`sales_by_cashier`)
- Auditoría ampliada para eventos sensibles:
  - `catalog.product.create|update|delete`
  - `catalog.product_image.create|update|delete`
  - `inventory.adjustment.create`
  - `investor.assignment.create|update|delete`
- Tests agregados para métricas/reportes y auditoría de catálogo/inventario.
- Módulo de gastos v1 completado:
  - CRUD `/api/v1/expenses/` (admin)
  - filtros por rango/categoría
  - auditoría `expenses.create|update|delete`
  - índices y constraint de monto positivo
- Reporte de ventas integrado con gastos:
  - `expenses_summary` (total + conteo + por categoría)
  - `net_sales_after_expenses`
- Tests de gastos y reporte con integración de gastos.
Seguimiento funcional (iterativo):
- ampliar reportería financiera avanzada según operación real (márgenes detallados, cortes ejecutivos adicionales).

### Fase 8 — Hardening release
Estado: ✅ Cerrada (scope backend)
Completado:
- Validaciones críticas y tests por módulo.
- Serving de estáticos admin con Whitenoise.
- Security hardening configurable por entorno en `settings`:
  - guard de `SECRET_KEY` inseguro con `DEBUG=False`
  - flags SSL/cookies/HSTS parametrizados
  - CORS configurable por `DJANGO_CORS_*`
- Optimización de queries/listados:
  - `LayawayViewSet` con `prefetch_related("payments")`
  - filtro temprano en `InventoryStockView` para evitar agregación global innecesaria
- Índices nuevos para carga real:
  - `sales`: status/confirmed_at, cashier/created_at, product en líneas, método/tipo en pagos
  - `audit`: action+created_at, entity_type+entity_id
  - `ledger`: investor+created_at, entry_type+created_at
  - `layaway/customercredit`: status+expires_at, phone/name_phone
- Colección API formal para QA: `docs/API_QA_COLLECTION.http`.
- Runbook operativo base: `docs/RUNBOOK.md`.
- Definition of Done v1 documentada: `docs/DOD_V1.md`.
Seguimiento operativo (no bloqueante del cierre backend):
- Revalidar CSRF/CORS con dominios reales al configurar staging/prod final.
- Capturar baseline p95 con tráfico real una vez esté activo el entorno objetivo.

## Mapeo rápido contra plan maestro (módulos)
- Catálogo: ✅
- Inventario: ✅
- Compras/Recepciones: ✅
- Ventas POS: ✅
- Apartados/Saldo: ✅
- Inversionistas/Ledger: ✅
- Gastos: ✅ CRUD + reportería base
- Métricas/reportes: 🟡 Parcial
- Usuarios/Roles/Accesos: ✅
- Catálogo web (solo visualización): ✅ Backend listo (endpoint público readonly)
