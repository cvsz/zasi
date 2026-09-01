.PHONY: all setup test test-api test-js test-all coverage clean build install server run docker-build docker-run ci help

PYTHON ?= python3
PIP ?= $(PYTHON) -m pip
PIP_FLAGS ?= --break-system-packages
PORT ?= 8080

all: setup test build

setup:
	$(PIP) install $(PIP_FLAGS) --upgrade build coverage
	$(PIP) install $(PIP_FLAGS) --no-deps wheel setuptools 2>/dev/null || true

test:
	$(PYTHON) -m unittest discover -s tests -q

test-api:
	$(PYTHON) -m unittest tests.test_api

test-js:
	node tests/test_components.js

test-all: test test-api test-js coverage

coverage:
	coverage run -m unittest discover -s tests -q
	coverage report -m

clean:
	rm -rf build/ dist/ *.egg-info .coverage htmlcov/ data/*.db

build: clean
	$(PYTHON) -m build

install: build
	$(PIP) install $(PIP_FLAGS) --no-deps --force-reinstall dist/*.whl 2>/dev/null || $(PIP) install --no-deps --force-reinstall dist/*.whl

server:
	ZASI_PORT=$(PORT) $(PYTHON) backend/server.py

run:
	$(PYTHON) main.py

docker-build:
	docker build -t zasi:32.0.0 .

docker-run:
	docker run -p 8080:8080 zasi:32.0.0

ci: test-all docker-build

help:
	@echo "ZASI Full-Stack Automation Makefile"
	@echo "  make setup       - Install build dependencies"
	@echo "  make test        - Run 165 unit tests"
	@echo "  make test-api    - Run backend REST/WebSocket integration tests"
	@echo "  make test-js     - Run React Router component structure tests"
	@echo "  make test-all    - Run all unit, integration, and UI tests + coverage"
	@echo "  make build       - Build wheel & sdist distributions"
	@echo "  make install     - Build and install wheel"
	@echo "  make server      - Start J.A.R.V.I.S. React Router & REST/MCP server"
	@echo "  make run         - Run dialectical pipeline"
	@echo "  make docker-build- Build Docker image"
