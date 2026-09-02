.PHONY: all setup test test-api test-control-plane test-js test-all coverage clean build sbom install server run docker-build docker-run ci help

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

test-control-plane:
	$(PYTHON) -m unittest tests.test_control_plane_core tests.test_control_plane_broker tests.test_control_plane_api tests.test_security_hardening tests.test_egress_security

test-js:
	node tests/test_components.js

test-all: test test-api test-js coverage

coverage:
	coverage run -m unittest discover -s tests -q
	coverage report -m

clean:
	rm -rf build/ dist/ *.egg-info .coverage htmlcov/ data/*.db

build:
	$(PYTHON) -m build

sbom:
	$(PYTHON) scripts/generate_sbom.py --output dist/zasi-sbom.cdx.json --resolve-installed

install: build
	$(PIP) install $(PIP_FLAGS) --no-deps --force-reinstall dist/*.whl 2>/dev/null || $(PIP) install --no-deps --force-reinstall dist/*.whl

server:
	ZASI_API_KEY="$${ZASI_API_KEY:?ZASI_API_KEY must be set}" ZASI_PORT=$(PORT) $(PYTHON) -m backend.app

run:
	ZASI_API_KEY="$${ZASI_API_KEY:?ZASI_API_KEY must be set}" $(PYTHON) -m backend.app

docker-build:
	docker build -t zasi:32.0.0 .

docker-run:
	docker run --rm -p 127.0.0.1:8080:8080 -e ZASI_API_KEY="$${ZASI_API_KEY:?ZASI_API_KEY must be set}" -e ZASI_CORS_ORIGINS="$${ZASI_CORS_ORIGINS:-http://localhost:8080}" zasi:32.0.0

ci: test-all sbom docker-build

help:
	@echo "ZASI Full-Stack Automation Makefile"
	@echo "  make setup       - Install build dependencies"
	@echo "  make test        - Run the Python test suite"
	@echo "  make test-api    - Run legacy compatibility tests"
	@echo "  make test-control-plane - Run governed API, broker, persistence, and security tests"
	@echo "  make test-js     - Run React Router component structure tests"
	@echo "  make test-all    - Run all unit, integration, and UI tests + coverage"
	@echo "  make build       - Build wheel & sdist distributions"
	@echo "  make sbom        - Generate a CycloneDX 1.5 dependency inventory"
	@echo "  make install     - Build and install wheel"
	@echo "  make server      - Start the authoritative authenticated ASGI control plane"
	@echo "  make run         - Start the authoritative authenticated ASGI control plane"
	@echo "  make docker-build - Build the non-root control-plane image"
