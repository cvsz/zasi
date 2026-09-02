#!/usr/bin/env bash
# ZASI governed control-plane installer.
# This installer is deliberately non-destructive: configuration is backed up
# before migration and build output is never removed unless explicitly asked.
set -Eeuo pipefail

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
PYTHON_CMD="${PYTHON_CMD:-python3}"
PROFILE="${ZASI_PROFILE:-local}"
CONFIG_PATH="${REPO_ROOT}/config/zasi_config.json"

die() {
    echo -e "${RED}[ERROR] $*${NC}" >&2
    exit 1
}

command -v "${PYTHON_CMD}" >/dev/null 2>&1 || die "python3 is required"
command -v npm >/dev/null 2>&1 || die "npm is required to build the bundled cockpit"
"${PYTHON_CMD}" -m pip --version >/dev/null 2>&1 || die "python3 pip is required"
"${PYTHON_CMD}" -c 'import build' >/dev/null 2>&1 || die "python-build is required; run: python3 -m pip install build"

echo -e "${BLUE}ZASI governed control-plane installer${NC}"
echo -e "${GREEN}[OK] Python $(${PYTHON_CMD} -c 'import sys; print(".".join(map(str, sys.version_info[:3])))') detected${NC}"

mkdir -p "${REPO_ROOT}/config" "${REPO_ROOT}/data" "${REPO_ROOT}/electron"

if [[ -e "${CONFIG_PATH}" ]]; then
    backup_path="${CONFIG_PATH}.bak.$(date -u +%Y%m%dT%H%M%SZ)"
    cp -p -- "${CONFIG_PATH}" "${backup_path}"
    echo -e "${GREEN}[OK] Existing configuration backed up to ${backup_path}${NC}"
    if [[ "${ZASI_OVERWRITE_CONFIG:-no}" != "yes" ]]; then
        echo -e "${YELLOW}[INFO] Existing configuration preserved; set ZASI_OVERWRITE_CONFIG=yes to migrate it.${NC}"
    fi
fi

if [[ ! -e "${CONFIG_PATH}" || "${ZASI_OVERWRITE_CONFIG:-no}" == "yes" ]]; then
    temp_config="$(mktemp "${REPO_ROOT}/config/.zasi_config.XXXXXX")"
    trap 'rm -f -- "${temp_config:-}"' EXIT
    umask 077
    {
        printf '{\n'
        printf '  "schema_version": 7,\n'
        printf '  "profile": %s,\n' "$(printf '%s' "${PROFILE}" | "${PYTHON_CMD}" -c 'import json,sys; print(json.dumps(sys.stdin.read()))')"
        printf '  "server_port": 8080,\n'
        printf '  "capability_claims": false,\n'
        printf '  "external_writes": "disabled",\n'
        printf '  "research_execution": "disabled",\n'
        printf '  "physical_actuation": "disabled"\n'
        printf '}\n'
    } >"${temp_config}"
    chmod 600 "${temp_config}"
    mv -f -- "${temp_config}" "${CONFIG_PATH}"
    trap - EXIT
    echo -e "${GREEN}[OK] Truthful profile configuration written${NC}"
fi

echo -e "${BLUE}[*] Installing locked frontend dependencies and building cockpit${NC}"
cd -- "${REPO_ROOT}"
npm ci --ignore-scripts
npm run build

echo -e "${BLUE}[*] Running structural and Python contract checks${NC}"
node tests/test_components.js
"${PYTHON_CMD}" -m unittest discover -s tests -q
"${PYTHON_CMD}" -m compileall -q backend src main.py

echo -e "${BLUE}[*] Building Python distribution${NC}"
"${PYTHON_CMD}" -m build

wheel_file="$(find "${REPO_ROOT}/dist" -maxdepth 1 -type f -name 'zasi-*.whl' -print | sort | head -n 1)"
[[ -n "${wheel_file}" ]] || die "no wheel was produced"
"${PYTHON_CMD}" -m pip install --upgrade "${wheel_file}"

"${PYTHON_CMD}" - <<'PY'
from backend.app import create_app
from src.control_plane.config import Settings

settings = Settings.from_mapping({
    "ZASI_PROFILE": "local",
    "ZASI_API_KEY": "installer-validation-only",
    "ZASI_CORS_ORIGINS": "http://127.0.0.1:8080",
})
app = create_app(settings=settings)
assert app.title == "ZASI Governed Control Plane"
print("[OK] authoritative application import and profile validation passed")
PY

echo -e "${GREEN}[SUCCESS] ZASI installed without deleting user configuration, databases, keys, backups, dist, or build output.${NC}"
echo -e "${YELLOW}Launch with: ZASI_API_KEY='<operator-secret>' ZASI_PROFILE=${PROFILE} zasi${NC}"
