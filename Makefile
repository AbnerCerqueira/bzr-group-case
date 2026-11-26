.PHONY: help sync audit audit-html clean-data clean-html lint format typecheck test test-sql check

help:
	@echo "Comandos disponíveis:"
	@echo "  make sync       - Sincroniza dependências via uv"
	@echo "  make audit      - Executa a auditoria no terminal"
	@echo "  make audit-html - Gera a visualização da auditoria em docs/auditoria.html"
	@echo "  make clean-data - Executa o pipeline de limpeza e gera data/clean/"
	@echo "  make clean-html - Executa a limpeza e gera o painel em docs/limpeza.html"
	@echo "  make lint       - Verifica lint e formatação (ruff)"
	@echo "  make format     - Formata e aplica correções automáticas (ruff)"
	@echo "  make typecheck  - Verifica tipos estáticos (basedpyright)"
	@echo "  make test       - Executa os testes Python (pytest)"
	@echo "  make test-sql   - Valida a migração SQL em PostgreSQL via Docker"
	@echo "  make check      - Executa lint, typecheck e test"

sync:
	uv sync

audit:
	uv run python -m bzr_group_case.auditoria

audit-html:
	uv run python -m bzr_group_case.auditoria --html

clean-data:
	uv run python -m bzr_group_case.limpeza

clean-html:
	uv run python -m bzr_group_case.limpeza --html

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

test-sql:
	bash sql/tests/validar_migracao.sh

check: lint typecheck test
