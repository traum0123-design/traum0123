.PHONY: install install-dev lint type test migrate docker-build docker-run precommit

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

docker-build:
	docker build -t payroll-portal:dev .

docker-run:
	docker run --rm -p 8000:8000 --env-file .env payroll-portal:dev

precommit:
	pre-commit install
	pre-commit run --all-files
