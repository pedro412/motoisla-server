# Moto Isla Server

Backend base de Moto Isla con **Django + DRF + JWT**, listo para correr en local con **Docker + PostgreSQL**.

## Stack
- Django 5.x
- Django REST Framework
- Simple JWT
- PostgreSQL 16
- Gunicorn
- Docker / Docker Compose

## Estructura principal
- `config/`: configuración Django.
- `apps/api_urls.py`: enrutado API `v1`.
- `apps/accounts`: usuario custom + roles.
- `apps/catalog`: productos e imágenes.
- `apps/inventory`: movimientos y stock.
- `apps/purchases`: recepciones y confirmación idempotente.
- `apps/sales`: ventas, confirmación, void y métricas.
- `apps/layaway`: apartados y saldo a favor.
- `apps/investors` + `apps/ledger`: perfil/ledger de inversionista.
- `apps/audit`: auditoría de acciones críticas.

## Levantar entorno local
1. Copia variables base:
   ```bash
   cp .env.example .env
   ```
2. Build + up:
   ```bash
   docker compose up --build
   ```
3. Ejecuta migraciones (primera vez):
   ```bash
   docker compose run --rm web python manage.py makemigrations
   docker compose run --rm web python manage.py migrate
   ```
4. Seed de roles:
   ```bash
   docker compose run --rm web python manage.py seed_roles
   ```

## Endpoints base
- Health: `GET /health/`
- JWT:
  - `POST /api/v1/auth/token/`
  - `POST /api/v1/auth/token/refresh/`
- Catálogo:
  - `GET/POST /api/v1/products/`
  - `GET/PATCH/DELETE /api/v1/products/{id}/`
  - `GET/POST /api/v1/product-images/`
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

## Comandos útiles
Con `Makefile`:
- `make up`
- `make down`
- `make logs`
- `make makemigrations`
- `make migrate`
- `make test`
- `make lint`

## Notas
- La API usa permisos por rol (`ADMIN`, `CASHIER`, `INVESTOR`) con `accounts.User.role`.
- Errores API se devuelven en formato estándar:
  - `code`, `detail`, `fields`
- Listados DRF usan paginación (`count`, `next`, `previous`, `results`).
