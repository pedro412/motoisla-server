# Security Checklist (Release v1)

## 1) Variables críticas de entorno (producción)
- `DJANGO_DEBUG=False`
- `DJANGO_SECRET_KEY=<valor seguro, largo y único>`
- `DJANGO_ALLOWED_HOSTS=<dominios reales>`
- `DJANGO_CSRF_TRUSTED_ORIGINS=https://<dominio-admin>,https://<dominio-pos>`
- `DJANGO_CORS_ALLOWED_ORIGINS=https://<dominio-admin>,https://<dominio-pos>`
- `DJANGO_CORS_ALLOW_ALL_ORIGINS=False`

## 2) Seguridad HTTP / cookies
- `DJANGO_SECURE_SSL_REDIRECT=True`
- `DJANGO_SESSION_COOKIE_SECURE=True`
- `DJANGO_CSRF_COOKIE_SECURE=True`
- `DJANGO_SECURE_HSTS_SECONDS=31536000` (o mayor según política)
- `DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS=True`
- `DJANGO_SECURE_HSTS_PRELOAD=True` (si aplica)

## 3) Verificaciones de despliegue
- Health check: `GET /health/` responde `200`.
- Admin accesible solo por HTTPS.
- JWT (`/api/v1/auth/token/`) funciona con credenciales válidas y rechaza inválidas.
- Confirmar que no hay secretos hardcodeados en `.env` versionado.
- Verificar rotación de secretos (DB/passwords) en proveedor de infraestructura.

## 4) Revisión de permisos
- `ADMIN`: acceso total operativo.
- `CASHIER`: sin acceso a operaciones administrativas sensibles.
- `INVESTOR`: solo lectura de su propio perfil/ledger.
- Verificar que `PATCH/PUT/DELETE` sobre `/api/v1/sales/{id}/` estén bloqueados (405).

## 5) Auditoría mínima obligatoria
- Eventos sensibles presentes:
  - catálogo: create/update/delete
  - imágenes: create/update/delete
  - inventario manual: adjustment.create
  - asignaciones inversionista: create/update/delete
  - ventas/anulación/descuentos

## 6) Evidencia previa a release
- Ejecutar: `docker compose run --rm web python manage.py test`
- Adjuntar resultado de pruebas.
- Adjuntar snapshot de variables de entorno no sensibles.
