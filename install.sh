#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${VENV_DIR:-${PROJECT_ROOT}/.venv}"
PYTHON_BIN="${PYTHON_BIN:-python3.11}"
PROFILE="${1:-sqlite}"
PIP_INSTALL_ARGS=()

case "${PROFILE}" in
  sqlite)
    INSTALL_TARGET="${PROJECT_ROOT}"
    PROFILE_SUMMARY="SQLite / default stdio profile"
    ;;
  postgres)
    INSTALL_TARGET="${PROJECT_ROOT}[postgres]"
    PROFILE_SUMMARY="Postgres profile (adds asyncpg)"
    ;;
  trusted-sse)
    INSTALL_TARGET="${PROJECT_ROOT}"
    PROFILE_SUMMARY="Trusted SSE profile (same package metadata as SQLite; launch with scribe-server-sse)"
    ;;
  dev)
    INSTALL_TARGET="${PROJECT_ROOT}[dev]"
    PROFILE_SUMMARY="Contributor profile (editable install with dev tools)"
    PIP_INSTALL_ARGS=(-e)
    ;;
  dev-postgres|postgres-dev)
    INSTALL_TARGET="${PROJECT_ROOT}[dev,postgres]"
    PROFILE_SUMMARY="Contributor + Postgres profile"
    PIP_INSTALL_ARGS=(-e)
    ;;
  *)
    echo "Usage: $0 [sqlite|postgres|trusted-sse|dev|dev-postgres]"
    exit 1
    ;;
esac

echo "==> Checking Python environment"
if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  echo "Error: ${PYTHON_BIN} not found. Please install Python 3.11+."
  exit 1
fi

if [ ! -d "${VENV_DIR}" ]; then
  echo "==> Creating virtual environment at ${VENV_DIR}"
  "${PYTHON_BIN}" -m venv "${VENV_DIR}"
fi

echo "==> Activating virtual environment"
# shellcheck disable=SC1090
source "${VENV_DIR}/bin/activate"

echo "==> Upgrading pip"
python -m pip install --upgrade pip

echo "==> Installing ${PROFILE_SUMMARY} from pyproject.toml"
python -m pip install "${PIP_INSTALL_ARGS[@]}" "${INSTALL_TARGET}"

echo "==> Installation complete. Activate the environment with:"
echo "     source ${VENV_DIR}/bin/activate"
echo "==> Installed entry points:"
echo "     scribe"
echo "     scribe-server"
echo "     scribe-server-sse"
