# Definition of Done (Backend v1)

## 1) Funcionalidad
- Reglas de negocio críticas del plan maestro implementadas y validadas.
- Endpoints versionados bajo `/api/v1/` con contrato estable.
- Errores API mantienen formato `code/detail/fields`.

## 2) Calidad técnica
- Tests automáticos pasan en CI/local:
  - unit/integration por módulos críticos
  - flujos de ventas, apartados, imports, inversionistas
- Sin regresiones en permisos por rol (`ADMIN`, `CASHIER`, `INVESTOR`).
- Migraciones aplicables desde cero y sobre base existente.

## 3) Seguridad
- Configuración de producción validada según `docs/SECURITY_CHECKLIST.md`.
- `DEBUG=False` en producción.
- Secretos y hosts configurados por entorno.
- HTTPS y cookies seguras activadas en producción.

## 4) Observabilidad y trazabilidad
- Eventos críticos auditados.
- Logs suficientes para diagnóstico operativo.
- Runbook de incidencias disponible (`docs/RUNBOOK.md`).

## 5) Operación y QA
- Colección API para pruebas manuales disponible (`docs/API_QA_COLLECTION.http`).
- Validación de endpoints críticos (auth, ventas, métricas, inventario, inversionistas).

## 6) Documentación
- `docs/PLAN_STATUS.md` y `docs/NEXT_STEPS.md` actualizados.
- Estado de release y pendientes explícitos.
