# Moto Isla Server

Backend de Moto Isla para operación de tienda: catálogo, inventario, compras, ventas POS, apartados, inversionistas/ledger, gastos y reportes.

Base técnica: **Django + DRF + JWT + PostgreSQL**, listo para correr local con Docker.

## Estado actual del backend
- Core backend v1 prácticamente cerrado para operación local.
- Módulos funcionales: catálogo, inventario, compras/imports, ventas, cancelación, apartados, inversionistas/ledger, gastos, auditoría, métricas y reportes.
- Endpoint público para frontend catálogo-only disponible (`/api/v1/public/catalog/`).
- Hardening base aplicado (settings de seguridad, checklist, runbook, colección QA, DoD).

## Lo más importante (reglas críticas)
- SKU único en catálogo.
- Venta confirmada es la que impacta stock/métricas/ledger.
- Reintentos de confirmación no deben duplicar impacto.
- Cancelación (`void`) revierte inventario y, para productos de inversionista, revierte también asignación/ledger.
- Descuento cajero >10% requiere override admin.
- Apartados vencidos pasan a saldo a favor, no reembolso en efectivo.

## Stack
- Django 5.x
- Django REST Framework
- Simple JWT
- PostgreSQL 16
- Gunicorn + Whitenoise
- Docker / Docker Compose

## Estructura principal
- `config/`: configuración Django.
- `apps/api_urls.py`: enrutado API `v1`.
- `apps/accounts`: usuario custom + roles.
- `apps/catalog`: productos, imágenes y catálogo público readonly.
- `apps/inventory`: movimientos y stock agregado.
- `apps/imports`: parse/edición/confirmación de factura pegada.
- `apps/purchases`: recepciones de compra.
- `apps/sales`: ventas, confirmación, anulación, métricas y reportes.
- `apps/layaway`: apartados y saldo a favor.
- `apps/investors` + `apps/ledger`: inversionistas, asignaciones y movimientos financieros.
- `apps/expenses`: gastos administrativos.
- `apps/audit`: auditoría de eventos críticos.

## Quickstart local
1. Copia variables base:
```bash
cp .env.example .env
```
2. Levanta entorno:
```bash
docker compose up --build
```
3. Migraciones iniciales:
```bash
docker compose run --rm web python manage.py makemigrations
docker compose run --rm web python manage.py migrate
```
4. Seed de roles:
```bash
docker compose run --rm web python manage.py seed_roles
```

## Comandos útiles
- `make up`
- `make down`
- `make logs`
- `make makemigrations`
- `make migrate`
- `make test`
- `make lint`
- `make checkdeploy`

## Endpoints clave
- Health:
  - `GET /health/`
- Auth:
  - `POST /api/v1/auth/token/`
  - `POST /api/v1/auth/token/refresh/`
- Catálogo interno:
  - `GET/POST /api/v1/products/`
  - `GET/PATCH/DELETE /api/v1/products/{id}/`
  - `GET/POST /api/v1/product-images/`
- Catálogo público readonly:
  - `GET /api/v1/public/catalog/`
  - `GET /api/v1/public/catalog/{sku}/`
- Inventario:
  - `GET/POST /api/v1/inventory/movements/`
  - `GET /api/v1/inventory/stocks/`
- Compras:
  - `GET/POST /api/v1/purchase-receipts/`
  - `POST /api/v1/purchase-receipts/{id}/confirm/`
- Ventas:
  - `GET/POST /api/v1/sales/`
  - `POST /api/v1/sales/{id}/confirm/`
  - `POST /api/v1/sales/{id}/void/`
  - `GET /api/v1/metrics/`
  - `GET /api/v1/reports/sales/`
- Gastos:
  - `GET/POST /api/v1/expenses/`
  - `GET/PATCH/DELETE /api/v1/expenses/{id}/`
- Apartados:
  - `GET/POST /api/v1/layaways/`
  - `POST /api/v1/layaways/{id}/settle/`
  - `POST /api/v1/layaways/{id}/expire/`
  - `POST /api/v1/customer-credits/{id}/apply/`
- Inversionistas:
  - `GET/POST /api/v1/investors/` (admin)
  - `GET/PATCH /api/v1/investors/{id}/` (admin)
  - `POST /api/v1/investors/{id}/deposit/` (admin)
  - `POST /api/v1/investors/{id}/withdraw/` (admin)
  - `POST /api/v1/investors/{id}/reinvest/` (admin)
  - `GET /api/v1/investors/{id}/ledger/` (admin)
  - `GET/POST /api/v1/investors/assignments/` (admin)
  - `GET /api/v1/investors/me/`
  - `GET /api/v1/investors/me/ledger/`

## Calidad y validación esperada antes de cambios grandes
- Ejecutar `make lint`.
- Ejecutar `make test`.
- Para checks de despliegue: `make checkdeploy`.
- Mantener contratos API existentes (`code`, `detail`, `fields` y paginación DRF).

## Pendientes y backlog actual (alto nivel)
- Seguimiento operativo post-hardening:
  - validar CORS/CSRF con dominios reales en staging/prod.
  - baseline de performance p95 con tráfico real.
- Reportería financiera avanzada (iterativa):
  - cortes/márgenes ejecutivos adicionales.
- Frontend:
  - consumir catálogo público y flujos POS/admin con contratos actuales.

## Convenciones
- Roles: `ADMIN`, `CASHIER`, `INVESTOR`.
- Error contract: `code`, `detail`, `fields`.
- Listados: `count`, `next`, `previous`, `results`.
- Rutas base de API: `/api/v1/`.

## Documentación extendida
- Índice general: `docs/README.md`
- Contexto para agentes: `docs/AGENT_CONTEXT.md`
- Estado contra plan maestro: `docs/PLAN_STATUS.md`
- Backlog ordenado: `docs/NEXT_STEPS.md`
- Seguridad de release: `docs/SECURITY_CHECKLIST.md`
- Runbook operativo: `docs/RUNBOOK.md`
- Colección QA: `docs/API_QA_COLLECTION.http`
- Definition of Done: `docs/DOD_V1.md`
