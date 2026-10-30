SHELL := /bin/bash
.DEFAULT_GOAL := help

# Automatically use .venv if it exists, otherwise fallback to system path
VENV_BIN := $(shell [ -d .venv/bin ] && echo ".venv/bin/" || echo "")
PYTHON := $(VENV_BIN)python3
PYTEST := $(VENV_BIN)pytest
PIP := $(VENV_BIN)pip

.PHONY: venv install test eval clean help

help:
	@echo "Autonomy Boundary Framework (ABF) - Build & Evaluation Targets"
	@echo "  make venv     - Create Python virtual environment (.venv)"
	@echo "  make install  - Install dependencies and package in editable mode"
	@echo "  make eval     - Run full test suite with duration profiling (72 invariants in ~0.11s)"
	@echo "  make test     - Run standard pytest suite"
	@echo "  make clean    - Remove build artifacts and pytest caches"

venv:
	python3 -m venv .venv
	$(PIP) install --upgrade pip

install:
	$(PIP) install --upgrade pip
	$(PIP) install -e ".[dev]"
	$(PIP) install pydantic cryptography

test:
	$(PYTEST) tests/ -v

eval:
	$(PYTEST) tests/ -v --durations=10

clean:
	rm -rf __pycache__ .pytest_cache .cache/*.tmp results/*.json build dist *.egg-info
