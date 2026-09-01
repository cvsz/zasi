.PHONY: all build setup config install test clean run help

PYTHON ?= python3
PIP ?= $(PYTHON) -m pip

help:
	@echo "ZASI v25.0.0 Build & Setup Automation"
	@echo "======================================"
	@echo "make all      - Full setup, config, test, build, and install"
	@echo "make setup    - Setup build dependencies and requirements"
	@echo "make config   - Configure environment and verify settings"
	@echo "make test     - Execute full 125-subsystem unit test suite"
	@echo "make build    - Package sdist and wheel into dist/"
	@echo "make install  - Install ZASI wheel into Python environment"
	@echo "make run      - Run complete 128-subsystem main.py pipeline"
	@echo "make clean    - Remove build artifacts, caches, and dist/"

setup:
	@echo "[*] Verifying build toolchain..."
	@$(PYTHON) -c "import setuptools, build; print('[✓] Python build & setuptools available')" 2>/dev/null || $(PIP) install --break-system-packages build setuptools wheel

config: setup
	@echo "[*] Configuring ZASI environment..."
	@mkdir -p config docs/generated
	@if [ ! -f config/zasi_config.json ]; then \
		echo '{"version": "25.0.0", "subsystems": 128, "environment": "production", "formal_verification": true}' > config/zasi_config.json; \
	fi
	@echo "[✓] Configuration initialized: config/zasi_config.json"

test: config
	@echo "[*] Running full 125-subsystem test suite..."
	@$(PYTHON) -m unittest discover -s tests -q
	@echo "[✓] All 125 test suites passed."

build: test
	@echo "[*] Building distribution packages..."
	@rm -rf dist/ build/ *.egg-info
	@$(PYTHON) -m build -q
	@echo "[✓] Build complete: dist/"
	@ls -lh dist/

install: build
	@echo "[*] Installing ZASI into environment..."
	@$(PIP) install --break-system-packages --no-deps --force-reinstall dist/zasi-25.0.0-py3-none-any.whl
	@echo "[✓] ZASI v25.0.0 installed successfully into environment."

all: setup config test build install
	@echo "=========================================================="
	@echo "[SUCCESS] ZASI v25.0.0 Build, Setup, Config & Install OK"
	@echo "=========================================================="

run:
	@$(PYTHON) main.py

clean:
	@rm -rf dist/ build/ *.egg-info __pycache__ src/__pycache__ tests/__pycache__ .pytest_cache
	@echo "[✓] Cleaned build artifacts."
