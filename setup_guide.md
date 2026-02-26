# OA-Station Setup Guide

## Prerequisites

- Operating System: macOS or Linux
- Python: 3.12+

## Quick Setup (Recommended)

```bash
cd station
bash start.sh
```

The script will:
1. Install `uv` if needed
2. Create a Python 3.12 virtual environment
3. Install Python dependencies
4. Start the station

On first run (when no `.env` file exists), the config UI opens automatically in your browser for setup.

## Manual Setup

### 1. Install `uv`

```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 2. Setup Python Environment

```bash
cd station
uv venv --python=3.12
uv pip install -r requirements.txt
```

### 3. Configure Environment

```bash
cp env.example .env
```

Edit `.env` and set at least:

```env
# Station identity
STATION_STATION_ID=station-my-station

# OpenRouter management key (required for ephemeral key issuance)
# Get yours at: https://openrouter.ai/docs/guides/overview/auth/management-api-keys
OPENROUTER_MANAGEMENT_KEY=<your-management-key>

# Ticket keys (auto-generated on first startup if not set)
# STATION_TOKEN_PUBLIC_KEY=<issuer-public-key>
# STATION_TOKEN_PRIVATE_KEY=<issuer-private-key>
```

### 4. Run the Station

```bash
cd station
.venv/bin/python run_station.py
```

## Verification

Once running:

- Local API Docs: http://localhost:18888/docs
- Config UI (if enabled): http://localhost:18888/config

To verify the station is working:

```bash
curl http://localhost:18888/api/tickets/issue/public-key
```

### Core API Endpoints

- `POST /api/request_key` (requires `Authorization: InferenceTicket ...`)
- `POST /api/tickets/ticket_request` (requires `Authorization: Bearer <token>`)
- `GET /api/tickets/issue/public-key`

### Ticket Issuance Notes

- Bearer token for `ticket_request` is generated on startup and visible via the config UI.
- `ticket_request` requires exactly 100 blinded requests per call.
- Ticket keys are auto-generated on first startup and saved to `ticket_keys.json`.

## Config UI

The station includes a web-based configuration UI for initial setup. Enable it with:

```env
STATION_ENABLE_CONFIG_UI=true
```

The config UI is restricted to localhost access only. On first run (when no `.env` exists), it is automatically enabled and opens in your browser.

## Troubleshooting

### Python version issues

- Verify Python 3.12+:

```bash
python3 --version
```

### Dependency installation issues

- Recreate venv and reinstall:

```bash
cd station
rm -rf .venv
uv venv --python=3.12
uv pip install -r requirements.txt
```

### Station fails to start

- Confirm `OPENROUTER_MANAGEMENT_KEY` is set in `station/.env` if using key issuance endpoints.
- Ticket keys are auto-generated if not provided. Check logs for errors if ticket services fail to initialize.

## Support

For issues or questions, open an issue at:
https://github.com/openanonymity/oa_station
