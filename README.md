# Open Anonymity Station

**OA Station** is a privacy-preserving inference proxy for AI models. It sits between users and inference providers, accepting anonymized requests authenticated by blind-signed inference tickets and issuing ephemeral, single-use API keys. Because each request arrives with a fresh, unlinkable credential, neither the station nor the upstream provider can trace requests back to a specific user.

This is a **reference implementation** -- a minimal, self-contained station that handles ephemeral key issuance. Spin up your own station and use it with the [OA Chat](https://github.com/openanonymity/oa-chat) client app.

Part of the [Open Anonymity](https://openanonymity.ai) project -- privacy infrastructure for AI.

## How It Works

1. A user obtains **inference tickets** (blind-signed tokens) from a ticket issuer
2. The user presents tickets to a station via `POST /api/request_key`
3. The station verifies the tickets (without learning who the user is) and issues a short-lived **ephemeral API key** via the configured inference provider
4. The user uses the ephemeral key to make AI inference requests directly

## Quick Start

Requires Python 3.12+ and a Unix-like OS (macOS or Linux).

```bash
cd station
bash start.sh
```

On first run (when no `.env` file exists), the config UI opens automatically in your browser for setup. Ticket keys are auto-generated on first startup if not configured.

For manual setup, see the [Setup Guide](setup_guide.md).

## API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/api/request_key` | POST | Exchange inference tickets for an ephemeral API key |
| `/api/tickets/ticket_request` | POST | Issue inference tickets (requires Bearer token) |
| `/api/tickets/issue/public-key` | GET | Get the ticket issuer's public key |

Full API docs available at `/docs` when running.

## Configuration

Copy `station/env.example` to `station/.env` and configure:

- **`OPENROUTER_MANAGEMENT_KEY`** -- Your OpenRouter management API key ([get one here](https://openrouter.ai/docs/guides/overview/auth/management-api-keys))
- **`STATION_STATION_ID`** -- Human-readable station identifier
- **`STATION_TOKEN_PUBLIC_KEY`** / **`STATION_TOKEN_PRIVATE_KEY`** -- Inference ticket keys (auto-generated if not set)

See `station/env.example` for all available options.

### Config UI

A localhost-only web-based configuration UI is available at `/config` for initial setup. It is **enabled by default** when using `start.sh`. To enable it manually:

```env
STATION_ENABLE_CONFIG_UI=true
```

## Documentation

- [Setup Guide](setup_guide.md) -- Detailed installation and configuration

## License

This project is licensed under the [GNU Affero General Public License v3.0](LICENSE).
