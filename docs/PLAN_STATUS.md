# Plan Maestro Status

Referencia: `plan-maestro-v1.md` (v1)

## Resumen ejecutivo
- Avance general estimado: **70-75% del backend v1**.
- Fases cerradas: **0, 1, 2, 3, 4, 5, 6**.
- Fases pendientes: **7 y 8**.

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

### Fase 7 — Auditoría + Métricas base
Estado: 🟡 Parcial
Completado:
- Audit log de acciones críticas.
- Métrica de ventas básica (`/api/v1/metrics/`).
Pendiente:
- Set de métricas gerenciales completas (top productos, métodos de pago detallados, cortes por periodo robustos).
- Cobertura ampliada de auditoría cruzada para todos los eventos de dominio.

### Fase 8 — Hardening release
Estado: 🟡 Parcial
Completado:
- Validaciones críticas y tests por módulo.
- Serving de estáticos admin con Whitenoise.
Pendiente:
- Checklist formal de seguridad de release.
- Optimización de queries en listados críticos.
- Colección API formal para QA/operación.
- Definition of Done v1 congelada por escrito.

## Mapeo rápido contra plan maestro (módulos)
- Catálogo: ✅
- Inventario: ✅
- Compras/Recepciones: ✅
- Ventas POS: ✅
- Apartados/Saldo: ✅
- Inversionistas/Ledger: ✅
- Gastos: 🟡 Base de modelo
- Métricas/reportes: 🟡 Parcial
- Usuarios/Roles/Accesos: ✅
- Catálogo web (solo visualización): ⏳ Depende de frontend
