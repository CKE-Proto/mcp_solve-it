.PHONY: install test test-unit test-integration lint typecheck format

install:
	pip install -e ".[dev]"

test: test-unit test-integration

test-unit:
	pytest tests/unit/ -v

test-integration:
	pytest tests/integration/ -v

lint:
	ruff check src/ tests/

typecheck:
	mypy src/mcp_chassis/

format:
	ruff format src/ tests/
	ruff check --fix src/ tests/
