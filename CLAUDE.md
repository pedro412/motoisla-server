# Moto Isla Server — Agent Context

## Two-repo system
This is one of two repos. The frontend lives in `motoisla-client` (Next.js).
The client never calls this API directly from the browser — it uses a Next.js proxy route.

## Stack
- Django 5.x, Python 3.12
- Django REST Framework + SimpleJWT
- PostgreSQL 16
- Gunicorn + Whitenoise
- Docker Compose (`web` + `db` services)

## Quickstart

```bash
make up                   # build + start containers
make migrate              # run migrations
make test                 # run test suite
make lint                 # run linter
make checkdeploy          # Django deployment checks

# One-time seeds (auto-run on container start, idempotent)
docker compose run --rm web python manage.py seed_roles
docker compose run --rm web python manage.py seed_suppliers_parsers
docker compose run --rm web python manage.py seed_product_taxonomy
```

## Apps

| App | Responsibility |
|---|---|
| `accounts` | Custom user, roles (ADMIN/CASHIER/INVESTOR), JWT auth |
| `catalog` | Products (SKU unique), images, brands/types, `cost_price` |
| `inventory` | Stock movements (PURCHASE/SALE/ADJUSTMENT/etc.), aggregated stock |
| `suppliers` | Suppliers + parser registry (e.g. MYESA) |
| `imports` | Invoice import staging: batch → parse → edit lines → confirm |
| `purchases` | Purchase receipts |
| `sales` | POS: Sale/SaleLine/Payment/VoidEvent/CardCommissionPlan, profitability snapshot |
| `layaway` | Customer (by phone), Layaway (multiproduct + lines), CustomerCredit, extensions |
| `investors` | Investor, InvestorAssignment (qty_assigned/qty_sold) |
| `ledger` | LedgerEntry (CAPITAL_IN/OUT, INVENTORY_TO_CAPITAL, PROFIT_SHARE, etc.) |
| `expenses` | Expense (FIXED/VARIABLE, PENDING/PAID/CANCELLED), FixedExpenseTemplate |
| `audit` | AuditLog for critical events |
| `common` | Shared permissions/exceptions |

## API base path: `/api/v1/`

See `README.md` for the full endpoint list with HTTP verbs and URL patterns.

## Key business rules (non-negotiable)

- **SKU unique** — no duplicate products
- **Sale confirm is idempotent** — enforced via unique key; retries must not double-impact stock/ledger
- **Void window**: 10 min for CASHIER; ADMIN can void anytime
- **Cashier discount >10%** requires admin override (username + password)
- **Card commissions**: stored in `CardCommissionPlan` table; NORMAL 2%, MSI_3 5.58%
- **Profitability**: on confirm, creates `SaleProfitabilitySnapshot` + `SaleLineProfitability`, updates `InvestorAssignment.qty_sold`, creates `LedgerEntry` rows. On void, creates compensatory reversal entries — **never deletes** records
- **Operating cost rate**: uses MTD_REAL (expenses_paid / sales_total, clamped 8–35%) if data meets threshold (≥$50k MXN, ≥20 sales); falls back to FALLBACK_BASE 17.5%
- **Investor profit split**: 50/50 of net profit; capital cost recovered as separate ledger entry
- **Layaway expiry**: 15 days; expired deposit → `CustomerCredit` (no cash refund)
- **Layaway REFUNDED**: when the originating confirmed sale is voided, the layaway state becomes `REFUNDED`

## Error contract (never break this)

All error responses: `{ code, detail, fields }`
All list responses: `{ count, next, previous, results }` (DRF standard pagination)

## Conventions

- Roles source of truth: Django `Group` (`ADMIN`, `CASHIER`, `INVESTOR`); `user.role` is a cache
- Language: backend/admin in English (`LANGUAGE_CODE = en-us`); UI labels in Spanish (frontend concern)
- Never break existing API contracts when adding features
- Before large changes: run `make lint` + `make test`; update `docs/PLAN_STATUS.md` and `docs/NEXT_STEPS.md`

## Extended documentation

| Doc | Purpose |
|---|---|
| `README.md` | Full endpoint reference, quickstart, recent notes |
| `docs/AGENT_CONTEXT.md` | Architecture summary + working commands |
| `docs/NEXT_STEPS.md` | Ordered backlog for next features |
| `docs/PLAN_STATUS.md` | Phase-by-phase completion status |
| `docs/SECURITY_CHECKLIST.md` | Pre-release security checklist |
| `docs/RUNBOOK.md` | Operational incident runbook |
| `docs/API_QA_COLLECTION.http` | QA request collection |
| `docs/DOD_V1.md` | Definition of Done v1 |
| `plan-maestro-v1.md` | Business rules source of truth |
