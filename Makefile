.PHONY: up down logs test lint migrate createsuperuser makemigrations shell checkdeploy

up:
	docker compose up --build

down:
	docker compose down

logs:
	docker compose logs -f

test:
	docker compose run --rm -e SKIP_COLLECTSTATIC=1 web python manage.py test

lint:
	docker compose run --rm web python -m compileall manage.py config apps

migrate:
	docker compose run --rm web python manage.py migrate

makemigrations:
	docker compose run --rm web python manage.py makemigrations

createsuperuser:
	docker compose run --rm web python manage.py createsuperuser

shell:
	docker compose run --rm web python manage.py shell

checkdeploy:
	docker compose run --rm \
		-e DJANGO_DEBUG=False \
		-e DJANGO_SECRET_KEY=prod-secret-key-change-this-9f3k2m8q1x7v6n4c0a5d2h9j6l1p4r8t \
		-e DJANGO_ALLOWED_HOSTS=example.com \
		-e DJANGO_CSRF_TRUSTED_ORIGINS=https://example.com \
		-e DJANGO_CORS_ALLOWED_ORIGINS=https://example.com \
		-e DJANGO_SECURE_SSL_REDIRECT=True \
		-e DJANGO_SESSION_COOKIE_SECURE=True \
		-e DJANGO_CSRF_COOKIE_SECURE=True \
		-e DJANGO_SECURE_HSTS_SECONDS=31536000 \
		-e DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS=True \
		-e DJANGO_SECURE_HSTS_PRELOAD=True \
		-e SKIP_COLLECTSTATIC=1 \
		web python manage.py check --deploy
