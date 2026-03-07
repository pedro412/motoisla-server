# Runbook Operativo (v1)

## 1) Comandos base
- Levantar: `make up`
- Bajar: `make down`
- Logs: `make logs`
- Migraciones: `make migrate`
- Tests: `make test`

## 2) Incidencias comunes

### API no responde
1. Verificar contenedores: `docker compose ps`
2. Revisar logs: `docker compose logs -f web db`
3. Validar salud: `curl http://localhost:8000/health/`

### Error de migraciones
1. Ejecutar: `docker compose run --rm web python manage.py showmigrations`
2. Aplicar pendientes: `docker compose run --rm web python manage.py migrate`
3. Reintentar endpoint afectado.

### Error de autenticación JWT
1. Confirmar usuario/rol existe.
2. Probar token:
   - `POST /api/v1/auth/token/`
   - `POST /api/v1/auth/token/refresh/`
3. Revisar reloj del host/servidor (desfase horario rompe validez temporal).

### Diferencias de stock
1. Consultar movimientos:
   - `GET /api/v1/inventory/movements/?product=<id>`
   - `GET /api/v1/inventory/stocks/?product=<id>`
2. Revisar eventos relacionados:
   - compras confirmadas
   - ventas confirmadas/anuladas
   - apartados (reserve/release)
3. Auditar acciones manuales en `AuditLog`.

### Métricas inconsistentes
1. Ejecutar reporte por rango:
   - `GET /api/v1/metrics/?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD`
   - `GET /api/v1/reports/sales/?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD`
2. Validar que solo ventas `CONFIRMED` entran en agregados.

### Balances de inversionistas inconsistentes
Si un balance de ledger no cuadra con lo esperado:
1. Correr reconciliación (solo lectura, sin efectos secundarios):
   ```bash
   docker compose run --rm web python manage.py reconcile_ledger
   ```
2. El comando reporta:
   - Balances capital/inventory/profit por inversionista.
   - `qty_sold` de cada `InvestorAssignment` vs la fuente de verdad en `SaleLineProfitability`.
   - Exit code 0 = todo consistente. Exit code 1 = hay mismatches (revisar output).
3. Si hay mismatch en `qty_sold`: revisar `SaleLineProfitability` para la asignación afectada y crear entrada compensatoria en ledger si aplica. **Nunca editar entradas de ledger existentes** (el modelo lo prohíbe a nivel de código).

## 3) Escalamiento
- Si hay pérdida de datos, congelar operación de escritura y exportar evidencia (logs + IDs afectados).
- Si hay impacto de seguridad, rotar secretos y bloquear acceso externo temporalmente.
