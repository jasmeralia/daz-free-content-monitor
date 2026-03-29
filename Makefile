PYTHON ?= .venv/bin/python

.PHONY: help venv venv-win lint test image clean

help: ## Show available targets
	@$(PYTHON) -c "\
import re, sys; \
lines = open('Makefile').readlines(); \
[print(f'  {m.group(1):<12} {m.group(2)}') \
 for line in lines \
 for m in [re.match(r'^([a-zA-Z_-]+):.*?## (.*)', line)] if m]"

venv: ## Create virtualenv and install dev dependencies (WSL/Linux)
	python3 -m venv .venv
	.venv/bin/pip install --upgrade pip
	.venv/bin/pip install -r requirements-dev.txt

venv-win: ## Create virtualenv and install dev dependencies (Windows)
	python -m venv .venv-win
	.venv-win\Scripts\pip install --upgrade pip
	.venv-win\Scripts\pip install -r requirements-dev.txt

lint: ## Run ruff, pylint, and mypy
	$(PYTHON) -m ruff check src tests
	$(PYTHON) -m ruff format --check src tests
	$(PYTHON) -m pylint src
	$(PYTHON) -m mypy src

test: ## Run tests with coverage
	$(PYTHON) -m pytest tests/ --cov=src --cov-report=term-missing -v

image: ## Build the Docker image
	docker build -t daz-free-content-monitor .

clean: ## Remove virtual environments and caches
	rm -rf .venv .venv-win .mypy_cache .ruff_cache .pytest_cache htmlcov .coverage
