# Agent Context (Moto Isla Server)

## 1. Objetivo del repositorio
Backend API de Moto Isla con Django + DRF + PostgreSQL para operación de tienda (POS), inventario, compras, apartados y ledger de inversionistas.

## 2. Stack actual
- Django 5.x
- Django REST Framework
- SimpleJWT
- PostgreSQL 16
- Gunicorn + Whitenoise
- Docker Compose (`web` + `db`)

## 3. Estructura de módulos
- `apps/accounts`: usuario custom, roles y seed de grupos.
- `apps/catalog`: productos e imágenes.
- `apps/inventory`: movimientos e inventario agregado.
- `apps/suppliers`: proveedores y parser por proveedor.
- `apps/imports`: staging/parse/confirm de factura.
- `apps/purchases`: recepciones de compra.
- `apps/sales`: ventas POS, pagos, confirmación, anulación.
- `apps/layaway`: apartados, liquidación, expiración, saldo a favor.
- `apps/investors`: inversionistas y asignaciones.
- `apps/ledger`: movimientos financieros de inversionista.
- `apps/audit`: auditoría de eventos críticos.
- `apps/expenses`: gastos (base).

## 4. Estado funcional (resumen)
Implementado y funcional hasta Fase 6 del plan por capas:
- Fase 0-1: base técnica, JWT, roles, permisos y error contract.
- Fase 2: catálogo + inventario.
- Fase 3: imports + compras con parse/confirm y validaciones.
- Fase 4: POS ventas con idempotencia, void window y override admin.
- Fase 5: apartados/saldo a favor con vigencia y reglas estrictas.
- Fase 6: inversionistas + ledger (depósito/retiro/reinversión + asignaciones).

## 5. Convenciones importantes
- Idioma de plataforma: admin y backend base en inglés (`LANGUAGE_CODE = en-us`).
- API errors: `code`, `detail`, `fields`.
- Roles fuente de verdad: `Group` (`ADMIN`, `CASHIER`, `INVESTOR`) con fallback a `user.role`.
- Rutas API bajo `/api/v1/`.
- Operación local recomendada con Docker.

## 6. Endpoints clave
- Auth: `/api/v1/auth/token/`, `/api/v1/auth/token/refresh/`
- Catalog: `/api/v1/products/`, `/api/v1/product-images/`
- Inventory: `/api/v1/inventory/movements/`, `/api/v1/inventory/stocks/`
- Imports: `/api/v1/import-batches/`, `/api/v1/import-lines/{id}/`
- Purchases: `/api/v1/purchase-receipts/`
- Sales: `/api/v1/sales/`, `/api/v1/metrics/`
- Layaway: `/api/v1/layaways/`, `/api/v1/customer-credits/`
- Investors: `/api/v1/investors/`, `/api/v1/investors/me/`

## 7. Comandos de trabajo
- `make up`
- `make migrate`
- `make test`
- `make lint`
- `docker compose run --rm web python manage.py seed_roles`

## 8. Admin (visibilidad operativa)
Registrado:
- accounts, catalog, inventory, purchases, sales, layaway, investors, ledger.

## 9. Riesgos actuales
- Aún faltan reportes gerenciales completos (fase 7).
- `expenses` existe como modelo base, sin módulo/reportería cerrada.
- Fase 8 backend cerrada:
  - checklist de seguridad documentado
  - colección API QA disponible
  - runbook y DoD v1 documentados
  - índices y optimizaciones de query en módulos críticos
- Seguimiento operativo pendiente fuera de desarrollo backend:
  - validar CSRF/CORS con dominios reales en staging/prod
  - capturar baseline de performance p95 con tráfico real
