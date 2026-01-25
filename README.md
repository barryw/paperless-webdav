# paperless-webdav

[![CI](https://ci.barrywalker.io/api/badges/barryw/paperless-webdav/status.svg)](https://ci.barrywalker.io/barryw/paperless-webdav)
[![GitHub release](https://img.shields.io/github/v/release/barryw/paperless-webdav)](https://github.com/barryw/paperless-webdav/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Container Registry](https://img.shields.io/badge/ghcr.io-barryw%2Fpaperless--webdav-blue)](https://github.com/barryw/paperless-webdav/pkgs/container/paperless-webdav)

A WebDAV bridge for [Paperless-ngx](https://docs.paperless-ngx.com/) that lets you mount your documents as a network drive, filtered by tags.

Perfect for tax season, audits, or any time you need to work with a subset of documents in your favorite file manager.

## Features

- **Tag-based shares** - Create shares that filter documents by Paperless tags
- **Mount anywhere** - Works with any WebDAV client (macOS Finder, Windows Explorer, Linux file managers, mobile apps)
- **Done tracking** - Move documents to a "done" folder to mark them as reviewed (adds a tag in Paperless)
- **Time-limited shares** - Set expiration dates for temporary access
- **Flexible authentication** - Supports Paperless-native auth or enterprise OIDC/LDAP (Authentik, Keycloak, etc.)
- **Caching** - Document content and metadata caching for fast directory listings
- **Admin UI** - Web interface for managing shares with real-time updates

## Architecture

```
┌─────────────────┐     HTTPS/WebDAV     ┌─────────────────────────────────────┐
│   File Manager  │ <------------------> │         paperless-webdav            │
│   (any OS)      │                      │  ┌─────────────┬─────────────────┐  │
└─────────────────┘                      │  │ Admin UI    │ WebDAV Server   │  │
                                         │  │ (8080)      │ (8081)          │  │
┌─────────────────┐     HTTPS/OIDC       │  │ FastAPI     │ wsgidav         │  │
│   Web Browser   │ <------------------> │  │ Jinja+HTMX  │                 │  │
│   (Admin)       │                      │  └──────┬──────┴────────┬────────┘  │
└─────────────────┘                      │         │               │           │
                                         │         v               v           │
                                         │  ┌─────────────────────────────┐   │
                                         │  │     PaperlessProvider       │   │
                                         │  │  (translates to API calls)  │   │
                                         │  └──────────────┬──────────────┘   │
                                         └─────────────────┼───────────────────┘
                                                           │
                    ┌──────────────────────────────────────┼──────────────────┐
                    │                                      │                  │
                    v                                      v                  v
           ┌──────────────┐                      ┌──────────────┐    ┌──────────────┐
           │  PostgreSQL  │                      │  Paperless   │    │  Authentik   │
           │  (shares,    │                      │  REST API    │    │  LDAP/OIDC   │
           │   tokens)    │                      └──────────────┘    │  (optional)  │
           └──────────────┘                                          └──────────────┘
```

## Quick Start

### Docker Compose

1. Clone the repository:
   ```bash
   git clone https://github.com/barryw/paperless-webdav.git
   cd paperless-webdav
   ```

2. Create your environment file:
   ```bash
   cp .env.example .env
   ```

3. Edit `.env` with your settings:
   ```bash
   # Required
   PAPERLESS_URL=http://your-paperless-instance:8000
   SECRET_KEY=generate-a-random-32-char-string-here

   # Generate with: python -c "import secrets; import base64; print(base64.b64encode(secrets.token_bytes(32)).decode())"
   ENCRYPTION_KEY=your-base64-encoded-32-byte-key
   ```

4. Start the services:
   ```bash
   docker compose up -d
   ```

5. Access the admin UI at `https://localhost` (or your configured domain)

### Kubernetes

See the [`k8s/`](k8s/) directory for example manifests. You'll need:

- A PostgreSQL database
- Secrets for `DATABASE_URL`, `ENCRYPTION_KEY`, `SECRET_KEY`
- Ingress for both admin (8080) and WebDAV (8081) ports

```bash
# Create the secret
kubectl create secret generic paperless-webdav \
  --from-literal=DATABASE_URL='postgresql+asyncpg://user:pass@host/db' \
  --from-literal=ENCRYPTION_KEY='your-base64-key' \
  --from-literal=SECRET_KEY='your-secret-key'

# Apply the manifests
kubectl apply -f k8s/
```

## Configuration

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `PAPERLESS_URL` | Yes | - | Base URL of your Paperless-ngx instance |
| `DATABASE_URL` | Yes | - | PostgreSQL connection string (use `postgresql+asyncpg://` for async) |
| `ENCRYPTION_KEY` | Yes | - | 32-byte base64-encoded key for encrypting stored tokens |
| `SECRET_KEY` | Yes | - | Secret key for session signing |
| `AUTH_MODE` | No | `paperless` | Authentication mode: `paperless` or `oidc` |
| `ADMIN_PORT` | No | `8080` | Port for the admin web UI |
| `WEBDAV_PORT` | No | `8081` | Port for the WebDAV server |
| `SESSION_EXPIRY_HOURS` | No | `24` | How long sessions remain valid |
| `COOKIE_SECURE` | No | `false` | Set `true` for HTTPS (required in production) |
| `LOG_LEVEL` | No | `INFO` | Logging level: DEBUG, INFO, WARNING, ERROR |
| `LOG_FORMAT` | No | `json` | Log format: `json` or `console` |

### OIDC Configuration (when `AUTH_MODE=oidc`)

| Variable | Required | Description |
|----------|----------|-------------|
| `OIDC_ISSUER` | Yes | OIDC provider URL (e.g., `https://auth.example.com/application/o/paperless-webdav/`) |
| `OIDC_CLIENT_ID` | Yes | OAuth2 client ID |
| `OIDC_CLIENT_SECRET` | Yes | OAuth2 client secret |
| `LDAP_URL` | No | LDAP server for WebDAV auth (e.g., `ldap://auth.example.com:389`) |
| `LDAP_BASE_DN` | No | LDAP base DN (e.g., `dc=ldap,dc=goauthentik,dc=io`) |
| `LDAP_BIND_DN` | No | Service account DN for LDAP searches |
| `LDAP_BIND_PASSWORD` | No | Service account password |

### Generating the Encryption Key

```bash
python -c "import secrets; import base64; print(base64.b64encode(secrets.token_bytes(32)).decode())"
```

## Authentication Modes

### Mode 1: Paperless-Native (Default)

Best for simple setups where Paperless is your only authentication source.

```bash
AUTH_MODE=paperless
```

**How it works:**
- Admin UI: Log in with your Paperless username and password
- WebDAV: Use the same Paperless credentials
- Your API token is automatically obtained from Paperless

### Mode 2: OIDC + LDAP (Enterprise)

Best for SSO environments using Authentik, Keycloak, or other identity providers.

```bash
AUTH_MODE=oidc
OIDC_ISSUER=https://auth.example.com/application/o/paperless-webdav/
OIDC_CLIENT_ID=your-client-id
OIDC_CLIENT_SECRET=your-client-secret
LDAP_URL=ldap://auth.example.com:389
LDAP_BASE_DN=dc=ldap,dc=goauthentik,dc=io
```

**How it works:**
- Admin UI: Redirects to your OIDC provider for login
- First login: You'll be prompted to enter your Paperless API token (see below)
- WebDAV: Authenticates against LDAP using your SSO credentials

## Finding Your Paperless API Token

Your Paperless API token is required for paperless-webdav to access your documents.

1. Log in to your Paperless-ngx instance
2. Click on your username in the top-right corner
3. Select **My Profile** (or go to `/profile`)
4. Scroll down to **API Token**
5. Click **Copy** to copy the token

![Paperless Token Location](https://docs.paperless-ngx.com/assets/screenshots/userprofile.png)

**In OIDC mode**, you'll be prompted to enter this token on your first login. The token is encrypted and stored securely in the database.

**In Paperless mode**, the token is obtained automatically when you log in.

## Usage

### Creating a Share

1. Log in to the admin UI
2. Click **New Share**
3. Configure your share:
   - **Name**: URL-safe name (e.g., `tax2025`)
   - **Include Tags**: Documents must have ALL of these tags
   - **Exclude Tags**: Documents must NOT have any of these tags
   - **Expires**: Optional expiration date
   - **Done Folder**: Enable to track reviewed documents
   - **Done Tag**: Tag applied when moving to done folder

### Mounting WebDAV

#### macOS Finder

1. Open Finder
2. Press `Cmd+K` or go to **Go → Connect to Server**
3. Enter: `https://your-webdav-domain/share-name`
4. Enter your credentials when prompted

#### Windows Explorer

1. Open File Explorer
2. Right-click **This PC** → **Map network drive**
3. Enter: `https://your-webdav-domain/share-name`
4. Check "Connect using different credentials"
5. Enter your credentials

#### Linux (GNOME Files)

1. Open Files
2. Press `Ctrl+L` to edit the location bar
3. Enter: `davs://your-webdav-domain/share-name`
4. Enter your credentials when prompted

#### Linux (Command Line)

```bash
# Install davfs2
sudo apt install davfs2

# Mount the share
sudo mount -t davfs https://your-webdav-domain/share-name /mnt/paperless

# Or add to /etc/fstab for persistent mounting
https://your-webdav-domain/share-name /mnt/paperless davfs user,noauto 0 0
```

### Working with Documents

- **Browse**: Navigate folders like any network drive
- **Open**: Double-click to open documents in your default app
- **Copy**: Drag documents to your local disk
- **Mark as Done**: Drag documents to the `done` folder (if enabled)

Documents moved to the done folder will have the configured "done tag" added in Paperless and will no longer appear in the main listing.

## Troubleshooting

### "401 Unauthorized" when connecting

- **Paperless mode**: Verify your Paperless username/password
- **OIDC mode**: Make sure you've entered your Paperless API token in the admin UI
- Check that your Paperless instance is accessible from paperless-webdav

### "Share not found" or "404"

- Verify the share name in the URL matches exactly (case-sensitive)
- Check if the share has expired
- Make sure you have access to the share (owner or allowed user)

### "Connection timed out"

- Verify `PAPERLESS_URL` is correct and accessible
- Check if Paperless is running and responsive
- Verify network connectivity between paperless-webdav and Paperless

### Documents not appearing

- Verify your Paperless API token has access to the documents
- Check that documents have the required tags (all `include_tags` must be present)
- Verify documents don't have any `exclude_tags`
- If using done folder, documents with the done tag won't appear in root

### WebDAV client shows empty folder

- Some clients cache directory listings - try refreshing
- Check the share configuration in the admin UI
- Verify the Paperless API returns documents with `curl`:
  ```bash
  curl -H "Authorization: Token YOUR_TOKEN" \
    "https://your-paperless/api/documents/?tags__name__all=tag1,tag2"
  ```

### OIDC login fails

- Verify `OIDC_ISSUER` URL is correct (should end with `/`)
- Check client ID and secret match your OIDC provider configuration
- Ensure the callback URL is configured in your OIDC provider:
  `https://your-admin-domain/auth/callback`

### LDAP authentication fails (OIDC mode)

- Verify `LDAP_URL` and `LDAP_BASE_DN` are correct
- Test LDAP connectivity:
  ```bash
  ldapsearch -x -H ldap://your-ldap:389 -b "dc=ldap,dc=example,dc=com" "(uid=username)"
  ```
- Check if your LDAP provider requires a bind DN for searches

### High memory usage

- Large shares with many documents may use more memory
- Consider enabling pagination in Paperless
- Check the cache settings (content cached for 5 minutes by default)

## Development

### Prerequisites

- Python 3.12+
- [uv](https://github.com/astral-sh/uv) package manager
- PostgreSQL (or use Docker Compose)

### Setup

```bash
# Clone the repo
git clone https://github.com/barryw/paperless-webdav.git
cd paperless-webdav

# Install dependencies
uv sync --all-extras

# Run tests
uv run pytest

# Run linting
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/

# Run type checking
uv run mypy src/
```

### Running Locally

```bash
# Start PostgreSQL
docker compose up -d db

# Run database migrations
uv run alembic upgrade head

# Start the application
uv run python -m paperless_webdav.main
```

### Project Structure

```
paperless-webdav/
├── src/paperless_webdav/
│   ├── api/              # FastAPI API routes
│   ├── auth/             # Authentication providers
│   ├── services/         # Business logic
│   ├── ui/               # Admin UI templates and routes
│   ├── cache.py          # Document caching
│   ├── config.py         # Configuration management
│   ├── database.py       # Database connection
│   ├── models.py         # SQLAlchemy models
│   ├── paperless_client.py  # Paperless API client
│   ├── webdav_auth.py    # WebDAV authentication
│   ├── webdav_provider.py   # WebDAV filesystem provider
│   └── webdav_server.py  # WebDAV server setup
├── tests/                # Test suite
├── k8s/                  # Kubernetes manifests
├── alembic/              # Database migrations
└── docs/                 # Documentation
```

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes with tests
4. Ensure CI passes (`uv run pytest && uv run ruff check src/ tests/`)
5. Commit with [conventional commits](https://www.conventionalcommits.org/)
6. Push and open a Pull Request

## License

MIT License - see [LICENSE](LICENSE) for details.

## Acknowledgments

- [Paperless-ngx](https://docs.paperless-ngx.com/) - The excellent document management system this project extends
- [wsgidav](https://wsgidav.readthedocs.io/) - The WebDAV library powering the file server
- [FastAPI](https://fastapi.tiangolo.com/) - The modern web framework for the admin UI
