# Sure Auto Categorizer

Autonomous service that finds **uncategorized transactions** in a
[Sure Finance](https://github.com/we-promise/sure) instance and assigns a category to each one
using an LLM (Groq), through Sure's REST API.

Transactions are assumed to already be in Sure (e.g. via an Open Banking connection). This service
only does the **auto-categorization** step.

## How it works

1. Fetch the category list from Sure.
2. Fetch all transactions with no category (transfers are skipped).
3. Send them to the LLM in batches, asking it to pick one existing category per transaction.
4. Write the chosen `category_id` back to each transaction (`PATCH /api/v1/transactions/{id}`).
5. Sleep `RUN_INTERVAL_SECONDS` and repeat (or exit if set to `0`).

It is idempotent: already-categorized transactions are never touched.

## Quick start

```bash
cp .env.example .env   # fill in the three required values
docker compose up -d
docker compose logs -f
```

## Configuration

All configuration is via environment variables (no config files).

| Variable | Required | Default | Description |
|---|---|---|---|
| `SURE_URL` | ✅ | — | Base URL of the Sure instance, e.g. `https://sure.example.com` |
| `SURE_API_KEY` | ✅ | — | Sure API key with `read_write` scope |
| `GROQ_API_KEY` | ✅ | — | Groq API key |
| `SURE_ACCOUNT_ID` | ❌ | _all accounts_ | Restrict processing to a single account id |
| `GROQ_MODEL` | ❌ | `llama-3.3-70b-versatile` | Groq chat model id |
| `GROQ_URL` | ❌ | `https://api.groq.com/openai/v1` | OpenAI-compatible base URL |
| `RUN_INTERVAL_SECONDS` | ❌ | `3600` | Seconds between runs. `0` = run once and exit |
| `BATCH_SIZE` | ❌ | `25` | Transactions per LLM request (1–100) |
| `DRY_RUN` | ❌ | `false` | Log proposed categories without writing them |
| `REQUEST_TIMEOUT` | ❌ | `60` | HTTP timeout (seconds) |
| `LOG_LEVEL` | ❌ | `INFO` | Loguru log level |

**Tip:** run once with `DRY_RUN=true RUN_INTERVAL_SECONDS=0` to preview assignments before
committing them.

## Deploy

`compose.yaml` pulls the prebuilt image from GitHub Container Registry:

```yaml
image: ghcr.io/aguyonp/sure-auto-categorizer:latest
```

```bash
docker compose pull && docker compose up -d
```

To build locally instead, comment the `image:` line and uncomment `build: .` in `compose.yaml`.

## CI / Registry

`.github/workflows/docker.yml` builds the image and pushes it to
`ghcr.io/<owner>/<repo>` on every push to `main` and on `v*` tags. No extra secrets needed —
it uses the built-in `GITHUB_TOKEN`. After the first successful run, make the GHCR package public
(or authenticate `docker pull`) so `docker compose pull` works.

## Local development

```bash
uv sync
uv run sure-auto-categorizer
```
