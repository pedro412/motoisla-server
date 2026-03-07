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
1. ✅ API de gastos recurrentes y variables.
2. ✅ Integración en reportería gerencial usando solo gastos `PAID`.
3. ✅ Tests de agregación por categoría, periodo y generación mensual.

## Prioridad 4 — Reportería financiera (siguiente iteración)
1. Consolidar reportería exacta de consumo por asignación/venta para inversionistas (fase 2).
2. Evaluar tabla explícita de consumos por venta para eliminar inferencias en métricas.
3. Exponer comparativos entre periodos para utilidad tienda vs inversionistas.

## Prioridad 5 — Soporte frontend catalog-only
1. ✅ Endpoint de catálogo público readonly (`/api/v1/public/catalog/`, `/api/v1/public/catalog/{sku}/`).
2. ✅ Rate limiting/caching básico para consulta pública.
3. Siguiente iteración:
- acordar contrato final con frontend web (campos/orden/filtros adicionales)
- evaluar cache externa (Redis/CDN) para tráfico alto

## Prioridad 6 — Seguimiento operativo
1. Validar CSRF/CORS con dominios reales en staging/prod.
2. Capturar baseline de performance (latencia p95 + query plans) con tráfico real.
3. Endurecer concurrencia en compras de inversionistas para evitar sobreasignación bajo requests simultáneos.

## Prioridad 7 — Ventas (siguiente iteración UX/operación)
1. Agregar filtros server-side para `GET /api/v1/sales/` (estatus, cajero, fecha, id).
2. Evaluar endpoint de cobro atómico (`create + confirm`) para evitar drafts huérfanos cuando falla la confirmación.
3. Exponer reportería de comisiones de tarjeta para utilidad operativa y conciliación.

## Prioridad 8 — Inversionistas (siguiente iteración operativa)
1. Exponer reinversión y filtros más finos de ledger para frontend.
2. Evaluar locking explícito por producto/asignación para compras concurrentes.

## Prioridad 9 — Integridad del ledger: inmutabilidad y reconciliación

> Objetivo: que el ledger sea la única fuente de verdad. Cualquier balance o cantidad derivada
> siempre debe poder recalcularse desde cero sumando entradas del ledger. Sin campos cacheados
> que puedan desincronizarse silenciosamente.

1. **Auditar campos mutables acoplados al ledger**: identificar todos los campos que se modifican junto con la creación de `LedgerEntry` (e.g. `InvestorAssignment.qty_sold`, snapshots de rentabilidad). Evaluar si pueden derivarse del ledger en lugar de almacenarse como estado mutable.
2. **Garantizar atomicidad total en operaciones financieras**: las operaciones `confirm` y `void` deben ejecutarse en una única transacción de base de datos (`atomic`). Si cualquier paso falla (creación de ledger entry, actualización de snapshot, cambio de qty_sold), todo hace rollback. No puede quedar un campo actualizado y una entrada de ledger sin crear.
3. **Comando de reconciliación** (`python manage.py reconcile_ledger`): recalcular balances desde cero sumando entradas del ledger y comparar contra campos cacheados. Reportar cualquier discrepancia. Equivalente al `git status` del estado financiero — debe poder correrse en cualquier momento sin efectos secundarios.
4. **Modo de solo lectura para entradas pasadas**: ningún código debe poder editar o eliminar un `LedgerEntry` ya creado. Solo se permiten entradas compensatorias nuevas. Agregar restricción explícita a nivel de modelo/servicio.
5. **Test de caos financiero**: simular fallos a mitad de `apply_sale_profitability` y `revert_sale_profitability` y verificar que el estado queda consistente o completamente revertido — nunca a medias.

> Riesgo sin esto: un fallo parcial puede dejar `qty_sold` o balances de inversionista
> desincronizados del ledger de forma silenciosa. El error no se detecta hasta que alguien
> revisa un reporte y los números no cuadran.

## Prioridad 10 — Cobertura de tests: lógica financiera crítica
1. Auditar cobertura de tests en `apps/sales/profitability.py` — funciones `apply_sale_profitability`, `revert_sale_profitability` y `build_sale_profitability_preview`.
2. Verificar casos borde: productos con mezcla de chunks STORE + múltiples inversionistas, venta con múltiples métodos de pago, void de venta con apartado liquidado.
3. Auditar cobertura en `apps/ledger` — entradas INVENTORY_TO_CAPITAL y PROFIT_SHARE generadas correctamente y sus reversiones compensatorias.
4. Añadir unit tests de lógica pura (cálculos de split, pesos por qty, comisión de tarjeta) separados de los integration tests — un bug en un cálculo no debe requerir leer un request completo para detectarse.
5. Asegurar que ningún escenario de void o re-confirmación pueda dejar ledger en estado inconsistente.

> Riesgo: un bug en esta lógica genera entradas de ledger incorrectas con impacto financiero real para inversionistas. Es el código de mayor riesgo del sistema.

## Prioridad 10 — Clientes / lealtad (backlog)
1. Diseñar programa de lealtad o descuentos basado en historial de compras del `Customer`.
2. Definir reglas de elegibilidad y trazabilidad para promociones por recurrencia.

## Notas para agentes
- No romper contratos actuales de API (`code/detail/fields`, paginación DRF).
- Mantener reglas de negocio ya cerradas en fases 3-6.
- Antes de cambios grandes, actualizar `docs/PLAN_STATUS.md` y este backlog.
- Recordar que cambios de UI del cliente (breadcrumbs, headers de detalle, etiquetas visuales) no requieren cambios de contrato salvo que se modifique el payload.
