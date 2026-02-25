# Moto Isla Server

Base sólida inicial para el backend de Moto Isla con **Django + DRF**, listo para correr en local con **Docker + PostgreSQL**.

## Stack inicial
- Django 5.x
- Django REST Framework
- PostgreSQL 16
- Gunicorn
- Docker / Docker Compose

## Estructura
- `config/`: configuración principal de Django.
- `apps/health/`: endpoint de health check (`/health/`).
- `docker-compose.yml`: orquestación de app + base de datos.
- `Dockerfile`: imagen de la app.
- `docker/entrypoint.sh`: migraciones automáticas al iniciar contenedor web.

## Levantar el entorno local
1. (Opcional) Copia variables base:
   ```bash
   cp .env.example .env
   ```
2. Inicia los servicios:
   ```bash
   docker compose up --build
   ```
3. Probar health check:
   - `http://localhost:8000/health/`

## Comandos útiles
- Crear superusuario:
  ```bash
  docker compose run --rm web python manage.py createsuperuser
  ```
- Ejecutar migraciones manualmente:
  ```bash
  docker compose run --rm web python manage.py migrate
  ```
- Detener servicios:
  ```bash
  docker compose down
  ```

## Notas
- El servicio `db` se inicia automáticamente junto con `web`.
- La persistencia de PostgreSQL se guarda en el volumen `postgres_data`.
