# Production Deployment

This guide covers deploying Apollos AI using the Docker Compose stack in `deploy/docker/`. It assumes you are deploying to a Linux server with Docker already installed.

## Prerequisites

- **Docker Engine** 24+ with the Compose V2 plugin (`docker compose`)
- **Architecture**: The app image is built for `linux/amd64`. ARM hosts (Apple Silicon, Graviton) require emulation or a native rebuild.
- **Ports**: 50080 (direct), 80/443 (with Caddy proxy)
- **Python 3** or **OpenSSL** on the host (for secret generation during setup)

## Quick Start

```bash
cd deploy/docker
./setup.sh            # guided first-time setup
```

The setup script:

1. Copies `.env.example` to `.env` (if `.env` does not exist).
2. Auto-generates `FLASK_SECRET_KEY` and `VAULT_MASTER_KEY`.
3. Prompts for admin email and password.
4. Pulls images and runs `docker compose up -d`.

It is safe to re-run. Existing `.env` values are never overwritten.

For manual setup without the script:

```bash
cd deploy/docker
cp .env.example .env
# Edit .env — at minimum set FLASK_SECRET_KEY, VAULT_MASTER_KEY, ADMIN_PASSWORD
docker compose up -d
```

## Compose Profiles

The stack supports three profiles that can be combined.

### Default (no profile) -- App Only

```bash
docker compose up -d
```

- Runs the Apollos AI container with SQLite for auth storage.
- Exposes port `HOST_PORT` (default 50080) directly.
- Suitable for single-user or internal deployments behind an existing reverse proxy.

### `proxy` -- Caddy HTTPS Reverse Proxy

```bash
docker compose --profile proxy up -d
# Or with the setup script:
./setup.sh --proxy
```

- Adds a Caddy container for TLS termination and security headers.
- Exposes ports 80 and 443 (plus 443/udp for HTTP/3).
- Caddy waits for the app health check before accepting traffic.
- Four TLS modes are available (configured in `Caddyfile` or via `setup.sh --proxy`):
  1. **Custom certificates** -- Place `cert.pem` and `key.pem` in `certs/`.
  2. **Automatic HTTPS** -- Let's Encrypt. Requires a public FQDN and ports 80/443 open.
  3. **Self-signed** -- `tls internal`. For internal environments that need HTTPS without a real CA.
  4. **HTTP-only** -- No TLS. For environments where TLS is terminated upstream.

When using the proxy profile, set `DOMAIN` in `.env` to your FQDN.

### `postgres` -- PostgreSQL Auth Database

```bash
docker compose --profile postgres up -d
# Or:
./setup.sh --postgres
```

- Adds a PostgreSQL 18 container (with pgvector) for the auth database.
- Replaces the default SQLite auth store.
- Requires two `.env` changes:
  ```
  POSTGRES_PASSWORD=<strong-password>
  AUTH_DATABASE_URL=postgresql://apollos:${POSTGRES_PASSWORD}@postgres:5432/apollos_auth
  ```
  The setup script handles this automatically.

### Combined -- Full Stack

```bash
docker compose --profile proxy --profile postgres up -d
# Or:
./setup.sh --proxy --postgres
```

Runs all three services: app, Caddy, and PostgreSQL.

## Environment Configuration

All configuration is in `deploy/docker/.env` (created from `.env.example`).

### Required Variables

| Variable | Purpose |
|---|---|
| `FLASK_SECRET_KEY` | Flask session signing. Must persist across restarts. |
| `VAULT_MASTER_KEY` | AES-256-GCM encryption for secrets at rest. |
| `ADMIN_EMAIL` | Bootstrap admin account email. |
| `ADMIN_PASSWORD` | Bootstrap admin account password. |

Generate cryptographic values with:

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

### Deployment Variables

| Variable | Default | Purpose |
|---|---|---|
| `IMAGE_TAG` | `latest` | App image tag. Pin to a release (e.g., `v1.0.0`) for stability. |
| `HOST_PORT` | `50080` | Host port for direct access (bypassing Caddy). |
| `DOMAIN` | `localhost` | FQDN for Caddy. Used in Caddyfile and CORS settings. |
| `POSTGRES_PASSWORD` | `changeme` | PostgreSQL password (profile `postgres` only). |

### API Keys

At least one LLM provider key is required. Set using the `API_KEY_{PROVIDER}` pattern:

```
API_KEY_ANTHROPIC=sk-ant-...
API_KEY_OPENAI=sk-...
```

Provider IDs match entries in `conf/model_providers.yaml`.

### Networking (Caddy Proxy)

When deploying behind Caddy with a custom domain, also configure:

- `CORS_ALLOWED_ORIGINS=https://your-domain.com`
- `ALLOWED_ORIGINS=https://your-domain.com`
- `SESSION_COOKIE_SECURE=true`

The setup script sets these automatically when a non-localhost `DOMAIN` is detected.

### Full Reference

See `deploy/docker/.env.example` for the complete annotated list, and `docs/reference/environment-variables.md` for the full catalog of 61+ settings overridable via `A0_SET_*` prefix.

## Health Checks

The app container exposes a `/health` endpoint used by Docker's built-in health check:

```yaml
healthcheck:
  test: ["CMD", "curl", "-sf", "http://localhost/health"]
  interval: 30s
  timeout: 5s
  start_period: 90s
  retries: 3
```

- **Start period**: 90 seconds. First startup includes model downloads and database migrations, which can take 60-90 seconds.
- **Caddy dependency**: The Caddy container uses `condition: service_healthy`, so it will not start accepting traffic until the app is ready.
- **PostgreSQL**: Has its own health check via `pg_isready` (10s interval, 5 retries).

Monitor health status:

```bash
docker compose ps             # STATUS column shows "healthy" or "starting"
docker inspect --format='{{.State.Health.Status}}' apollos-ai
curl -sf http://localhost:50080/health
```

## Volumes and Data

| Named Volume | Mount Point | Contents |
|---|---|---|
| `apollos-ai-data` | `/a0/usr` | User data, settings, workdir, memory databases, `.env` |
| `apollos-ai-caddy-data` | `/data` | TLS certificates (Let's Encrypt), OCSP staples |
| `apollos-ai-caddy-config` | `/config` | Caddy runtime configuration |
| `apollos-ai-postgres-data` | `/var/lib/postgresql` | PostgreSQL database files |

All volumes are Docker named volumes and persist across `docker compose down`. They are only removed with `docker compose down -v` or `docker volume rm`.

### Backups

Back up the critical volumes:

```bash
# App data (settings, memory, workdir)
docker run --rm -v apollos-ai-data:/data -v "$(pwd)":/backup alpine \
  tar czf /backup/apollos-data-backup.tar.gz -C /data .

# PostgreSQL (if using postgres profile)
docker exec apollos-ai-db pg_dump -U apollos apollos_auth > apollos-auth-backup.sql
```

### Custom CA Certificates

To trust internal certificate authorities (e.g., enterprise PKI for a LiteLLM proxy):

1. Place PEM files in `deploy/docker/certs/ca/`.
2. Set in `.env`:
   ```
   REQUESTS_CA_BUNDLE=/usr/local/share/ca-certificates/custom/your-ca.pem
   ```

The `certs/ca/` directory is mounted read-only into the container.

## Security Checklist

- [ ] **Secrets generated**: `FLASK_SECRET_KEY`, `VAULT_MASTER_KEY`, and `ADMIN_PASSWORD` are set to unique, random values. Never reuse across environments.
- [ ] **Image pinned**: `IMAGE_TAG` is set to a specific release tag, not `latest`.
- [ ] **Secure cookies**: `SESSION_COOKIE_SECURE=true` when serving over HTTPS.
- [ ] **Non-root container**: The app image runs as a non-root user by default.
- [ ] **Log rotation**: JSON file logging with `max-size: 10m` and `max-file: 3` is configured in the compose file.
- [ ] **Firewall**: Only expose ports 80/443 (with Caddy) or 50080 (without). Block direct access to PostgreSQL (port 5432 is not published).
- [ ] **CORS origins**: `CORS_ALLOWED_ORIGINS` and `ALLOWED_ORIGINS` are set to your exact domain (not `*`).
- [ ] **PostgreSQL password**: Changed from the default `changeme` to a strong random value.
- [ ] **`.env` file permissions**: Restrict to owner-only read (`chmod 600 .env`).
- [ ] **TLS certificates**: If using custom certs, the `certs/` directory is mounted read-only.

## Updating

Pull the latest image and recreate containers:

```bash
cd deploy/docker
docker compose pull
docker compose --profile proxy --profile postgres up -d
```

Omit `--profile` flags you are not using. Docker Compose only recreates containers whose image has changed.

To pin to a specific release, set `IMAGE_TAG` in `.env`:

```
IMAGE_TAG=v1.2.0
```

Then pull and restart:

```bash
docker compose pull && docker compose up -d
```

### Rollback

To revert to a previous version, change `IMAGE_TAG` and restart:

```bash
# In .env
IMAGE_TAG=v1.1.0
```

```bash
docker compose up -d
```

The `apollos-ai-data` volume persists across updates. Database migrations run automatically on startup.

## Troubleshooting

**Container fails health check**: Check logs with `docker compose logs apollos-ai`. Common causes: missing API keys, port conflicts, insufficient memory.

**Caddy returns 502**: The app has not passed its health check yet. Wait for the 90-second start period, or check app logs.

**PostgreSQL connection refused**: Verify `AUTH_DATABASE_URL` uses the Docker service hostname `postgres` (not `localhost`), and that `POSTGRES_PASSWORD` matches in both the variable and the connection string.

**Permission denied on volumes**: Ensure the Docker daemon has access to the `deploy/docker/` directory, particularly `certs/` and `Caddyfile`.
