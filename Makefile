.PHONY: help sync lint format typecheck test check

help:
	@echo "Comandos disponíveis:"
	@echo "  make sync       - Sincroniza dependências via uv"
	@echo "  make lint       - Verifica lint e formatação (ruff)"
	@echo "  make format     - Formata e aplica correções automáticas (ruff)"
	@echo "  make typecheck  - Verifica tipos estáticos (basedpyright)"
	@echo "  make test       - Executa os testes (pytest)"
	@echo "  make check      - Executa lint, typecheck e test"

sync:
	uv sync

lint:
	uv run ruff check .
	uv run ruff format --check .

format:
	uv run ruff format .
	uv run ruff check --fix .

typecheck:
	uv run basedpyright

test:
	uv run pytest

check: lint typecheck test
