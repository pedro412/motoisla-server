# Next Steps (Ordered Backlog)

Este backlog mantiene el orden del plan original y deja tareas ejecutables para siguientes agentes.

## Prioridad 1 — Cerrar Fase 7 (Auditoría + Métricas)
1. ✅ Expandir endpoint de métricas (`/api/v1/metrics/`):
- ventas por rango de fechas
- ticket promedio por rango
- top productos por unidades e importe
- desglose por método de pago
2. ✅ Crear endpoint de reporte base admin readonly (`/api/v1/reports/sales/`).
3. 🟡 Completar auditoría de eventos faltantes:
- ✅ cambios sensibles de catálogo
- ✅ ajustes manuales de inventario
- ✅ operaciones manuales de ledger/inversionista (asignaciones auditadas)
4. ✅ Añadir tests de consistencia base de métricas vs ventas confirmadas.
5. Nuevo siguiente bloque:
- extender reporte para incluir gastos (cuando módulo CRUD de gastos esté listo)
- sumar pruebas de filtros límite (`top_limit`, rangos inválidos, respuesta vacía)

## Prioridad 2 — Cerrar Fase 8 (Hardening)
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
5. Pendiente de cierre final Fase 8:
- validar configuración CSRF/CORS con dominios reales de frontend en staging/prod
- capturar baseline de performance con datos reales (latencia y query plans)

## Prioridad 3 — Completar módulo de gastos (v1)
1. API CRUD de gastos.
2. Integración en métricas gerenciales.
3. Tests de agregación por categoría y periodo.

## Prioridad 4 — Soporte frontend catalog-only
1. Endpoint de catálogo público readonly (si se decide separarlo de auth).
2. Rate limiting/caching básico para consulta pública.

## Notas para agentes
- No romper contratos actuales de API (`code/detail/fields`, paginación DRF).
- Mantener reglas de negocio ya cerradas en fases 3-6.
- Antes de cambios grandes, actualizar `docs/PLAN_STATUS.md` y este backlog.
