.PHONY: install install-dev lint type test migrate docker-build docker-run precommit manage seed-demo downgrade

install:
	python3 -m pip install -r requirements.lock --require-hashes

install-dev:
	python3 -m pip install -r requirements-dev.txt

lint:
	ruff check .

type:
	PYTHONPATH=. mypy .

test:
	PYTHONPATH=. pytest -q

migrate:
	DATABASE_URL=sqlite:///./payroll_portal/app.db alembic upgrade head

makemigration:
	python scripts/make_migration.py -m "update"

seed-demo:
	PYTHONPATH=. python scripts/manage.py seed-demo

downgrade:
	DATABASE_URL=sqlite:///./payroll_portal/app.db python scripts/manage.py downgrade

manage:
	python scripts/manage.py -h

docker-build:
	docker build -t payroll-portal:dev .

docker-run:
	docker run --rm -p 8000:8000 --env-file .env payroll-portal:dev

precommit:
	pre-commit install
	pre-commit run --all-files
