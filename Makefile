.PHONY: up down logs test lint migrate createsuperuser makemigrations shell

up:
	docker compose up --build

down:
	docker compose down

logs:
	docker compose logs -f

test:
	docker compose run --rm web python manage.py test

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
