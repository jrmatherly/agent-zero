#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════
# Apollos AI — Docker Compose Setup Script
# ═══════════════════════════════════════════════════════════════════════
#
# Guided first-time setup:
#   1. Creates .env from .env.example (if not exists)
#   2. Auto-generates cryptographic secrets
#   3. Prompts for admin credentials
#   4. Pulls images and starts services
#
# Usage:
#   ./setup.sh                    # App only (SQLite)
#   ./setup.sh --proxy            # App + Caddy HTTPS
#   ./setup.sh --postgres         # App + PostgreSQL
#   ./setup.sh --proxy --postgres # Full stack
#
# Safe to re-run — will not overwrite existing .env or secrets.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ─── Colors ───────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

info()  { echo -e "${BLUE}[INFO]${NC}  $*"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }

# ─── Parse arguments ──────────────────────────────────────────────────
PROFILES=()
for arg in "$@"; do
    case "$arg" in
        --proxy)    PROFILES+=(proxy) ;;
        --postgres) PROFILES+=(postgres) ;;
        --help|-h)
            echo "Usage: $0 [--proxy] [--postgres]"
            echo ""
            echo "  --proxy     Enable Caddy HTTPS reverse proxy"
            echo "  --postgres  Enable PostgreSQL auth database"
            exit 0
            ;;
        *) error "Unknown argument: $arg"; exit 1 ;;
    esac
done

# ─── Check prerequisites ─────────────────────────────────────────────
info "Checking prerequisites..."

if ! command -v docker &>/dev/null; then
    error "Docker is not installed. See https://docs.docker.com/engine/install/"
    exit 1
fi

if ! docker compose version &>/dev/null; then
    error "Docker Compose V2 is not available. Update Docker or install the compose plugin."
    exit 1
fi

ok "Docker and Compose are available."

# ─── Generate secret helper ──────────────────────────────────────────
generate_hex() {
    python3 -c "import secrets; print(secrets.token_hex(32))" 2>/dev/null \
        || openssl rand -hex 32 2>/dev/null \
        || head -c 32 /dev/urandom | xxd -p -c 64
}

generate_password() {
    python3 -c "import secrets, string; print(''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(24)))" 2>/dev/null \
        || openssl rand -base64 18 2>/dev/null \
        || head -c 18 /dev/urandom | base64
}

# ─── Configure Caddy TLS helper ──────────────────────────────────────
configure_caddy_tls() {
    local mode="$1"
    local caddyfile="Caddyfile"

    # Normalize: comment out all active site-address and tls-directive lines
    # (already-commented lines are unaffected by these substitutions)
    local TAB
    TAB="$(printf '\t')"
    sed -i.bak \
        -e 's|^{[$]DOMAIN|# {$DOMAIN|' \
        -e 's|^http://{[$]DOMAIN|# http://{$DOMAIN|' \
        -e "s|^${TAB}tls /etc/caddy/certs/|${TAB}# tls /etc/caddy/certs/|" \
        -e "s|^${TAB}tls internal|${TAB}# tls internal|" \
        "$caddyfile"

    # Activate the desired lines based on mode
    case "$mode" in
        1)  # Custom certificates
            sed -i.bak \
                -e 's|^# {[$]DOMAIN|{$DOMAIN|' \
                -e "s|^${TAB}# tls /etc/caddy/certs/|${TAB}tls /etc/caddy/certs/|" \
                "$caddyfile"
            ;;
        2)  # Automatic HTTPS (Let's Encrypt — no tls directive needed)
            sed -i.bak -e 's|^# {[$]DOMAIN|{$DOMAIN|' "$caddyfile"
            ;;
        3)  # Self-signed HTTPS
            sed -i.bak \
                -e 's|^# {[$]DOMAIN|{$DOMAIN|' \
                -e "s|^${TAB}# tls internal|${TAB}tls internal|" \
                "$caddyfile"
            ;;
        4)  # HTTP-only
            sed -i.bak -e 's|^# http://{[$]DOMAIN|http://{$DOMAIN|' "$caddyfile"
            ;;
    esac

    rm -f "${caddyfile}.bak"
}

# ─── Create .env ──────────────────────────────────────────────────────
ENV_CREATED=false
if [ -f .env ]; then
    ok ".env already exists — skipping creation."
else
    ENV_CREATED=true
    info "Creating .env from .env.example..."
    cp .env.example .env

    # Auto-generate FLASK_SECRET_KEY if blank
    if grep -q '^FLASK_SECRET_KEY=$' .env; then
        SECRET=$(generate_hex)
        sed -i.bak "s/^FLASK_SECRET_KEY=$/FLASK_SECRET_KEY=${SECRET}/" .env
        ok "Generated FLASK_SECRET_KEY"
    fi

    # Auto-generate VAULT_MASTER_KEY if blank
    if grep -q '^VAULT_MASTER_KEY=$' .env; then
        SECRET=$(generate_hex)
        sed -i.bak "s/^VAULT_MASTER_KEY=$/VAULT_MASTER_KEY=${SECRET}/" .env
        ok "Generated VAULT_MASTER_KEY"
    fi

    # Clean up sed backup files
    rm -f .env.bak

    ok ".env created with auto-generated secrets."
fi

# ─── Prompt for admin credentials ─────────────────────────────────────
if grep -q '^ADMIN_PASSWORD=$' .env 2>/dev/null; then
    echo ""
    info "Configure admin account:"
    read -rp "  Admin email [admin@example.com]: " ADMIN_EMAIL
    ADMIN_EMAIL="${ADMIN_EMAIL:-admin@example.com}"
    sed -i.bak "s|^ADMIN_EMAIL=.*|ADMIN_EMAIL=${ADMIN_EMAIL}|" .env

    read -rsp "  Admin password (leave blank to auto-generate): " ADMIN_PASSWORD
    echo ""
    if [ -z "$ADMIN_PASSWORD" ]; then
        ADMIN_PASSWORD=$(generate_password)
        info "Generated admin password: ${ADMIN_PASSWORD}"
        warn "Save this password — it will not be shown again."
    fi
    sed -i.bak "s|^ADMIN_PASSWORD=$|ADMIN_PASSWORD=${ADMIN_PASSWORD}|" .env
    rm -f .env.bak

    ok "Admin credentials configured."
fi

# ─── PostgreSQL password ──────────────────────────────────────────────
if [[ " ${PROFILES[*]} " =~ " postgres " ]]; then
    if grep -q '^# POSTGRES_PASSWORD=$' .env 2>/dev/null; then
        PG_PASS=$(generate_password)
        # Uncomment and set POSTGRES_PASSWORD
        sed -i.bak "s|^# POSTGRES_PASSWORD=$|POSTGRES_PASSWORD=${PG_PASS}|" .env
        # Uncomment AUTH_DATABASE_URL
        sed -i.bak 's|^# AUTH_DATABASE_URL=|AUTH_DATABASE_URL=|' .env
        rm -f .env.bak
        ok "Generated PostgreSQL password and enabled AUTH_DATABASE_URL."
    fi
fi

# ─── TLS mode selection (proxy only) ─────────────────────────────────
TLS_MODE=""
if [[ " ${PROFILES[*]} " =~ " proxy " ]]; then
    if [ "$ENV_CREATED" = true ]; then
        # First run — prompt for TLS mode
        echo ""
        info "TLS mode for Caddy reverse proxy:"
        echo "  1) Custom certificates — provide cert.pem and key.pem in certs/"
        echo "  2) Automatic HTTPS — Let's Encrypt (requires public FQDN + ports 80/443)"
        echo "  3) Self-signed HTTPS — local development with HTTPS"
        echo "  4) HTTP-only — local development without TLS"
        read -rp "  Select [1-4] (default: 1): " TLS_MODE
        TLS_MODE="${TLS_MODE:-1}"

        case "$TLS_MODE" in
            1|2|3|4) ;;
            *) warn "Invalid choice '$TLS_MODE', defaulting to 1"; TLS_MODE=1 ;;
        esac

        configure_caddy_tls "$TLS_MODE"
        ok "Configured Caddyfile for TLS mode $TLS_MODE"
    else
        # Re-run — detect TLS mode from Caddyfile
        if grep -q '^http://' Caddyfile 2>/dev/null; then
            TLS_MODE=4
        elif grep -q '^[[:space:]]*tls internal' Caddyfile 2>/dev/null; then
            TLS_MODE=3
        elif grep -q '^[[:space:]]*tls /etc/caddy/certs/' Caddyfile 2>/dev/null; then
            TLS_MODE=1
        else
            TLS_MODE=2
        fi
    fi
fi

# ─── Protocol-aware CORS for custom domain ───────────────────────────
if [[ " ${PROFILES[*]} " =~ " proxy " ]]; then
    # Determine URL scheme based on TLS mode
    if [ "$TLS_MODE" = "4" ]; then
        PROTO="http"
    else
        PROTO="https"
    fi

    DOMAIN_VAL=$(grep '^DOMAIN=' .env 2>/dev/null | cut -d= -f2)
    if [ -n "$DOMAIN_VAL" ] && [ "$DOMAIN_VAL" != "localhost" ]; then
        if grep -q '^# CORS_ALLOWED_ORIGINS=' .env 2>/dev/null; then
            sed -i.bak "s|^# CORS_ALLOWED_ORIGINS=.*|CORS_ALLOWED_ORIGINS=${PROTO}://${DOMAIN_VAL}|" .env
            rm -f .env.bak
            ok "Set CORS_ALLOWED_ORIGINS=${PROTO}://${DOMAIN_VAL}"
        fi

        # ALLOWED_ORIGINS (CSRF)
        if grep -q '^# ALLOWED_ORIGINS=' .env 2>/dev/null; then
            sed -i.bak "s|^# ALLOWED_ORIGINS=.*|ALLOWED_ORIGINS=${PROTO}://${DOMAIN_VAL}|" .env
            rm -f .env.bak
            ok "Set ALLOWED_ORIGINS=${PROTO}://${DOMAIN_VAL}"
        fi

        # SESSION_COOKIE_SECURE (only for HTTPS modes)
        if [ "$TLS_MODE" != "4" ]; then
            if grep -q '^# SESSION_COOKIE_SECURE=' .env 2>/dev/null; then
                sed -i.bak "s|^# SESSION_COOKIE_SECURE=.*|SESSION_COOKIE_SECURE=true|" .env
                rm -f .env.bak
                ok "Set SESSION_COOKIE_SECURE=true"
            fi
        fi

        # MCP_SERVER_BASE_URL
        if grep -q '^# MCP_SERVER_BASE_URL=' .env 2>/dev/null; then
            sed -i.bak "s|^# MCP_SERVER_BASE_URL=.*|MCP_SERVER_BASE_URL=${PROTO}://${DOMAIN_VAL}|" .env
            rm -f .env.bak
            ok "Set MCP_SERVER_BASE_URL=${PROTO}://${DOMAIN_VAL}"
        fi

        # APP_BASE_URL
        if grep -q '^# APP_BASE_URL=' .env 2>/dev/null; then
            sed -i.bak "s|^# APP_BASE_URL=.*|APP_BASE_URL=${PROTO}://${DOMAIN_VAL}|" .env
            rm -f .env.bak
            ok "Set APP_BASE_URL=${PROTO}://${DOMAIN_VAL}"
        fi

        # OIDC_REDIRECT_URI
        if grep -q '^# OIDC_REDIRECT_URI=' .env 2>/dev/null; then
            sed -i.bak "s|^# OIDC_REDIRECT_URI=.*|OIDC_REDIRECT_URI=${PROTO}://${DOMAIN_VAL}/auth/callback|" .env
            rm -f .env.bak
            ok "Set OIDC_REDIRECT_URI=${PROTO}://${DOMAIN_VAL}/auth/callback"
        fi
    fi
fi

# ─── Certs directory ──────────────────────────────────────────────────
if [[ " ${PROFILES[*]} " =~ " proxy " ]]; then
    mkdir -p certs/ca
    case "$TLS_MODE" in
        1)
            if [ ! -f certs/cert.pem ] || [ ! -f certs/key.pem ]; then
                warn "No TLS certificates found in certs/"
                warn "Place your cert.pem and key.pem there before starting."
            else
                ok "TLS certificates found in certs/"
            fi
            ;;
        2)  ok "Using automatic HTTPS (Let's Encrypt) — no certificate files needed." ;;
        3)  ok "Using self-signed TLS (Caddy internal) — no certificate files needed." ;;
        4)  ok "Using HTTP-only mode — no certificate files needed." ;;
    esac
fi

# ─── Build compose command ────────────────────────────────────────────
COMPOSE_CMD="docker compose"
for profile in "${PROFILES[@]+"${PROFILES[@]}"}"; do
    COMPOSE_CMD+=" --profile $profile"
done

# ─── Pull and start ──────────────────────────────────────────────────
echo ""
info "Pulling images..."
$COMPOSE_CMD pull

echo ""
info "Starting services..."
$COMPOSE_CMD up -d

echo ""
ok "Apollos AI is starting up."
info "Check status:  $COMPOSE_CMD ps"
info "View logs:     $COMPOSE_CMD logs -f"
info "Health check:  curl -sf http://localhost:\${HOST_PORT:-50080}/health"
echo ""
warn "First startup may take 60-90 seconds (initializing services)."
