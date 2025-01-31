.PHONY: up restart down uv-commit

up-env:
	docker compose -f docker/docker-compose.yml up -d --build

restart-env:
	docker compose -f docker/docker-compose.yml restart

down-env:
	docker compose -f docker/docker-compose.yml down

uv-commit:
	uv pip compile pyproject.toml -o requirements.txt
