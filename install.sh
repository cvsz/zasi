#!/usr/bin/env bash
set -e

echo "========================================================="
echo "           ZASI Automated Setup & Installer              "
echo "========================================================="

# 1. Check Python version
PYTHON_CMD="python3"
if ! command -v $PYTHON_CMD &> /dev/null; then
    echo "[Error] Python 3 is not installed or not in PATH."
    exit 1
fi

PY_VER=$($PYTHON_CMD -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "[✓] Python version $PY_VER detected."

# 2. Install local package
echo "[*] Installing ZASI package into environment..."
pip install -e . --break-system-packages --quiet --no-warn-script-location 2>/dev/null || \
pip install -e . --quiet --no-warn-script-location 2>/dev/null || \
echo "[i] Running directly with PYTHONPATH (zero-dependency mode)."

# 3. Run self-tests
echo "[*] Running verification test suite..."
PYTHONPATH=. $PYTHON_CMD -m unittest discover -s tests

echo "========================================================="
echo "[SUCCESS] ZASI installation and build verified!"
echo "Run: 'python3 main.py' or 'zasi' to start."
echo "========================================================="
