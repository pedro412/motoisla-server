# Next Steps (Ordered Backlog)

Este backlog mantiene el orden del plan original y deja tareas ejecutables para siguientes agentes.

## Prioridad 1 — Cerrar Fase 7 (Auditoría + Métricas)
1. Expandir endpoint de métricas:
- ventas por rango de fechas
- ticket promedio por rango
- top productos por unidades e importe
- desglose por método de pago
2. Crear endpoints de reporte base para admin (solo lectura).
3. Completar auditoría de eventos faltantes:
- cambios sensibles de catálogo
- ajustes manuales de inventario
- operaciones de ledger manuales (ya parciales)
4. Añadir tests de consistencia de métricas vs ventas confirmadas.

## Prioridad 2 — Cerrar Fase 8 (Hardening)
1. Security checklist:
- revisar settings de prod (DEBUG, allowed hosts, secrets)
- validar CSRF/CORS según cliente real
2. Performance:
- revisar `select_related/prefetch_related` en endpoints de mayor uso
- agregar índices faltantes detectados por uso real
3. Operación:
- crear colección de requests (HTTP file o Postman) para QA
- documentar runbook de incidencias básicas
4. Calidad:
- definir y documentar DoD v1 final

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
