# Next Steps (Ordered Backlog)

Este backlog mantiene el orden del plan original y deja tareas ejecutables para siguientes agentes.

## Prioridad 1 — Fase 7 (Auditoría + Métricas) cerrada
1. ✅ Métricas ampliadas (`/api/v1/metrics/`) por rango/productos/pagos.
2. ✅ Reporte admin (`/api/v1/reports/sales/`) por día/cajero.
3. ✅ Integración de gastos en reportes (`expenses_summary`, `net_sales_after_expenses`).
4. ✅ Auditoría ampliada (catálogo, inventario, inversionistas y gastos).
5. ✅ Cobertura de tests de regresión para métricas/reportes y gastos.

## Prioridad 2 — Fase 8 (Hardening) cerrada
1. ✅ Security checklist:
- checklist documentado en `docs/SECURITY_CHECKLIST.md`
- settings de prod endurecidos (`DEBUG`, hosts, secrets, CSRF/CORS, SSL/cookies/HSTS)
2. ✅ Performance:
- revisión aplicada de `select_related/prefetch_related` y filtros tempranos
- índices agregados en módulos críticos (sales/audit/ledger/layaway)
3. ✅ Operación:
- colección de requests QA creada (`docs/API_QA_COLLECTION.http`)
- runbook de incidencias documentado (`docs/RUNBOOK.md`)
4. ✅ Calidad:
- DoD v1 documentada (`docs/DOD_V1.md`)
5. Seguimiento operativo post-cierre:
- validar configuración CSRF/CORS con dominios reales de frontend en staging/prod
- capturar baseline de performance con datos reales (latencia y query plans)

## Prioridad 3 — Módulo de gastos (v1) cerrado
1. ✅ API CRUD de gastos.
2. ✅ Integración en reportería gerencial base.
3. ✅ Tests de agregación por categoría y periodo.

## Prioridad 4 — Soporte frontend catalog-only
1. ✅ Endpoint de catálogo público readonly (`/api/v1/public/catalog/`, `/api/v1/public/catalog/{sku}/`).
2. ✅ Rate limiting/caching básico para consulta pública.
3. Siguiente iteración:
- acordar contrato final con frontend web (campos/orden/filtros adicionales)
- evaluar cache externa (Redis/CDN) para tráfico alto

## Prioridad 5 — Seguimiento operativo
1. Validar CSRF/CORS con dominios reales en staging/prod.
2. Capturar baseline de performance (latencia p95 + query plans) con tráfico real.

## Notas para agentes
- No romper contratos actuales de API (`code/detail/fields`, paginación DRF).
- Mantener reglas de negocio ya cerradas en fases 3-6.
- Antes de cambios grandes, actualizar `docs/PLAN_STATUS.md` y este backlog.
