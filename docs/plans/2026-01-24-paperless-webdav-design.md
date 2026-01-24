# paperless-webdav Design Document

**Date:** 2026-01-24
**Status:** Draft
**Author:** Barry (with Claude)

## Problem Statement

Accessing documents in Paperless-ngx during tax season (or similar bulk-retrieval scenarios) is cumbersome through the web UI. There's no native way to:

- Mount a filtered subset of documents as a network share
- Access documents directly from any file manager without copying
- Track which documents have been reviewed/processed
- Create time-limited access to document collections

## Solution Overview

**paperless-webdav** is a standalone bridge service that exposes Paperless-ngx documents via WebDAV, filtered by tags. Users create "shares" that define which documents are visible, with optional workflow features like expiration dates and "done" tracking.

### Key Features

- **Tag-based shares**: Define shares by including/excluding Paperless tags
- **WebDAV access**: Mount shares from any OS file manager
- **Done tracking**: Optional folder to mark documents as processed
- **Time-limited shares**: Automatic expiration (e.g., April 16th for tax docs)
- **Flexible auth**: Supports Paperless-native auth or enterprise OIDC/LDAP

## Architecture

```
┌─────────────────┐     HTTPS/WebDAV     ┌─────────────────────────────────────┐
│   File Manager  │ ◀──────────────────▶ │         paperless-webdav            │
│   (any OS)      │                      │  ┌─────────────┬─────────────────┐  │
└─────────────────┘                      │  │ Admin UI    │ WebDAV Server   │  │
                                         │  │ (8080)      │ (8081)          │  │
┌─────────────────┐     HTTPS/OIDC       │  │ FastAPI     │ wsgidav         │  │
│   Web Browser   │ ◀──────────────────▶ │  │ Jinja+HTMX  │                 │  │
│   (Admin)       │                      │  └──────┬──────┴────────┬────────┘  │
└─────────────────┘                      │         │               │           │
                                         │         ▼               ▼           │
                                         │  ┌─────────────────────────────┐   │
                                         │  │     PaperlessProvider       │   │
                                         │  │  (translates to API calls)  │   │
                                         │  └──────────────┬──────────────┘   │
                                         └─────────────────┼───────────────────┘
                                                           │
                    ┌──────────────────────────────────────┼──────────────────┐
                    │                                      │                  │
                    ▼                                      ▼                  ▼
           ┌──────────────┐                      ┌──────────────┐    ┌──────────────┐
           │  PostgreSQL  │                      │  Paperless   │    │  Authentik   │
           │  (shares,    │                      │  REST API    │    │  LDAP/OIDC   │
           │   tokens)    │                      └──────────────┘    └──────────────┘
           └──────────────┘
```

## Components

### 1. Admin UI (Port 8080)

**Purpose:** Web interface for managing shares and user settings.

**Technology:** FastAPI + Jinja2 + HTMX + Tailwind CSS

**Features:**
- Authentik OIDC login (or Paperless-native auth)
- First-login Paperless API token collection (OIDC mode only)
- Create/edit/delete shares
- Tag selection via Paperless API (autocomplete dropdown)
- Share expiration configuration
- Done folder configuration
- Real-time updates without page refreshes

### 2. WebDAV Server (Port 8081)

**Purpose:** Expose shares as mountable WebDAV endpoints.

**Technology:** wsgidav with custom PaperlessProvider

**Endpoints:**
```
https://webdav.example.com/{share-name}/
https://webdav.example.com/{share-name}/{done-folder}/
```

**Operations:**
| WebDAV Operation | Paperless Action |
|------------------|------------------|
| LIST directory   | Query documents by tags |
| GET file         | Download document (original or archived) |
| MOVE to done     | Add done tag to document |
| PROPFIND         | Return document metadata |

### 3. PaperlessProvider

**Purpose:** Translate WebDAV filesystem operations to Paperless API calls.

**Responsibilities:**
- Authenticate API requests using user's stored token
- Query documents matching share's tag filters
- Stream document downloads
- Apply tags when documents are moved to done folder
- Enforce share expiration and permissions

### 4. Database Schema

```sql
-- Users (linked to auth provider)
CREATE TABLE users (
    id UUID PRIMARY KEY,
    external_id VARCHAR(255) NOT NULL UNIQUE,  -- Authentik/Paperless user ID
    paperless_token_encrypted BYTEA,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Shares
CREATE TABLE shares (
    id UUID PRIMARY KEY,
    name VARCHAR(63) NOT NULL UNIQUE,  -- alphanumeric + dash
    owner_id UUID REFERENCES users(id),
    include_tags JSONB NOT NULL,       -- ["tax", "2025"]
    exclude_tags JSONB DEFAULT '[]',
    expires_at TIMESTAMPTZ,
    read_only BOOLEAN DEFAULT true,
    done_folder_enabled BOOLEAN DEFAULT false,
    done_folder_name VARCHAR(63) DEFAULT 'done',
    done_tag VARCHAR(63),
    allowed_users JSONB DEFAULT '[]',  -- additional users who can access
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Audit log
CREATE TABLE audit_log (
    id UUID PRIMARY KEY,
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    event_type VARCHAR(50) NOT NULL,   -- share_created, document_accessed, etc.
    user_id UUID REFERENCES users(id),
    share_id UUID REFERENCES shares(id),
    ip_address INET,
    user_agent TEXT,
    details JSONB
);

-- Indexes
CREATE INDEX idx_shares_name ON shares(name);
CREATE INDEX idx_shares_owner ON shares(owner_id);
CREATE INDEX idx_shares_expires ON shares(expires_at) WHERE expires_at IS NOT NULL;
CREATE INDEX idx_audit_timestamp ON audit_log(timestamp);
CREATE INDEX idx_audit_user ON audit_log(user_id);
```

## Share Configuration Model

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| name | string | Share path (alphanumeric + dash, max 63 chars) | `tax2025` |
| include_tags | string[] | Documents must have ALL these tags | `["tax", "2025"]` |
| exclude_tags | string[] | Documents must NOT have any of these | `["draft"]` |
| expires_at | datetime | Hard cutoff, share stops working | `2026-04-16T00:00:00Z` |
| read_only | boolean | Disable uploads/modifications | `true` |
| done_folder_enabled | boolean | Enable done subfolder | `true` |
| done_folder_name | string | Custom name for done folder | `completed` |
| done_tag | string | Tag applied when moved to done | `reviewed` |
| allowed_users | string[] | Additional users who can access | `["spouse"]` |

### Document Filtering Logic

```
Root listing:
  - has ALL tags in include_tags
  - has NONE of tags in exclude_tags
  - has NOT done_tag (if done folder enabled)

Done folder listing:
  - has ALL tags in include_tags
  - has done_tag
```

## Authentication

### Mode 1: Paperless-Native (Default)

```
AUTH_MODE=paperless
```

- Admin UI: Login with Paperless username/password
- Token acquisition: Automatic via POST to `/api/token/`
- WebDAV: Validate credentials against Paperless API
- Simplest setup for single-user or Paperless-only environments

### Mode 2: OIDC + LDAP (Enterprise)

```
AUTH_MODE=oidc
```

- Admin UI: Authentik (or other) OIDC login
- Token acquisition: User manually provides Paperless API token on first login
- WebDAV: Validate credentials against Authentik LDAP
- Required for SSO environments where Paperless uses OIDC-only auth

### Authentication Flow (OIDC Mode)

```
┌─────────────┐     ┌─────────────────┐     ┌───────────┐
│   Browser   │     │ paperless-webdav│     │ Authentik │
└──────┬──────┘     └────────┬────────┘     └─────┬─────┘
       │                     │                    │
       │  GET /admin         │                    │
       │────────────────────▶│                    │
       │                     │                    │
       │  302 → Authentik    │                    │
       │◀────────────────────│                    │
       │                     │                    │
       │  OIDC login flow    │                    │
       │─────────────────────┼───────────────────▶│
       │                     │                    │
       │  Redirect + code    │                    │
       │◀────────────────────┼────────────────────│
       │                     │                    │
       │  GET /callback?code │                    │
       │────────────────────▶│                    │
       │                     │  Exchange code     │
       │                     │───────────────────▶│
       │                     │  ID token          │
       │                     │◀───────────────────│
       │                     │                    │
       │  (first login?)     │                    │
       │  Prompt for token   │                    │
       │◀────────────────────│                    │
       │                     │                    │
       │  POST token         │                    │
       │────────────────────▶│                    │
       │                     │  Store encrypted   │
       │  Admin UI ready     │                    │
       │◀────────────────────│                    │
```

### WebDAV Authentication Flow (OIDC Mode)

```
┌─────────────┐     ┌─────────────────┐     ┌───────────┐     ┌───────────┐
│ File Manager│     │ paperless-webdav│     │ Authentik │     │ Paperless │
└──────┬──────┘     └────────┬────────┘     │   LDAP    │     │    API    │
       │                     │              └─────┬─────┘     └─────┬─────┘
       │  PROPFIND /tax2025  │                    │                 │
       │────────────────────▶│                    │                 │
       │                     │                    │                 │
       │  401 Unauthorized   │                    │                 │
       │◀────────────────────│                    │                 │
       │                     │                    │                 │
       │  (auth dialog)      │                    │                 │
       │  PROPFIND + Basic   │                    │                 │
       │────────────────────▶│                    │                 │
       │                     │  LDAP bind         │                 │
       │                     │───────────────────▶│                 │
       │                     │  bind success      │                 │
       │                     │◀───────────────────│                 │
       │                     │                    │                 │
       │                     │  Lookup user token │                 │
       │                     │  (from DB)         │                 │
       │                     │                    │                 │
       │                     │  GET /api/documents?tags=...        │
       │                     │─────────────────────────────────────▶│
       │                     │  Document list                       │
       │                     │◀─────────────────────────────────────│
       │                     │                    │                 │
       │  207 Multi-Status   │                    │                 │
       │◀────────────────────│                    │                 │
```

## Security

### Authentication Controls

- **No anonymous access**: All endpoints require authentication
- **No local users**: Auth delegated to Paperless or OIDC provider
- **Rate limiting**: 5 failed attempts → 15-minute IP lockout
- **Session expiry**: Configurable (default 24h), forced re-auth

### Token Security

- **Encryption at rest**: AES-256-GCM for stored Paperless tokens
- **Key management**: Encryption key from Kubernetes Secret, never in DB
- **No token logging**: Tokens excluded from all log output and error messages

### Network Security

- **TLS required**: No HTTP listener, TLS termination at ingress or service
- **Non-root execution**: Container runs as unprivileged user
- **Read-only filesystem**: Container filesystem is read-only (tmpfs for /tmp)
- **mTLS optional**: Ingress can require client certificates for additional security

### Authorization

- **User-scoped tokens**: Every Paperless API call uses the requesting user's token
- **Share ownership**: Shares are scoped to creator's Paperless permissions
- **Explicit access**: Additional users must be explicitly added to share's allowed_users
- **Hard expiration**: Expired shares return 404 immediately, no grace period

### Input Validation

- **Share names**: Alphanumeric + dash only, max 63 characters
- **Tag names**: Validated against Paperless API, no freeform entry
- **Path traversal**: WebDAV layer prevents directory escape attacks
- **SQL injection**: Parameterized queries via SQLAlchemy ORM

### Audit Logging

All security-relevant events logged in JSON format for Graylog ingestion:

```json
{
  "timestamp": "2026-01-24T10:30:00Z",
  "level": "INFO",
  "event_type": "document_accessed",
  "user_id": "barry",
  "share_id": "tax2025",
  "document_id": "12345",
  "ip_address": "192.168.1.100",
  "user_agent": "Microsoft-WebDAV-MiniRedir/10.0.19041"
}
```

**Logged events:**
- `auth_success`, `auth_failure` - Authentication attempts
- `share_created`, `share_updated`, `share_deleted` - Share management
- `document_accessed`, `document_downloaded` - Document access
- `document_moved_to_done` - Workflow actions
- `token_updated` - User token changes

**Never logged:**
- Passwords or tokens
- Document content
- Full file paths on disk

## Technology Stack

| Component | Technology | Rationale |
|-----------|------------|-----------|
| Language | Python 3.11+ | Matches wsgidav, mature ecosystem |
| Web framework | FastAPI | Modern async, good OIDC libraries |
| WebDAV server | wsgidav | Mature, supports custom providers |
| Templates | Jinja2 | Standard, good FastAPI integration |
| Interactivity | HTMX | Real-time updates without SPA complexity |
| Styling | Tailwind CSS | Responsive, utility-first |
| Database | PostgreSQL | Existing cluster infrastructure |
| ORM | SQLAlchemy 2.0 | Async support, type safety |
| Auth (OIDC) | Authlib | Well-maintained, good docs |
| Auth (LDAP) | python-ldap | Standard library for LDAP |
| Encryption | cryptography | AES-GCM implementation |
| Logging | structlog | Structured JSON output |
| Container base | python:3.11-slim | Balance of size and compatibility |

## Configuration

### Environment Variables

```yaml
# Core
PAPERLESS_URL: https://paperless.example.com
DATABASE_URL: postgresql://user:pass@host/dbname
ENCRYPTION_KEY: <32-byte base64 string from k8s secret>

# Ports
ADMIN_PORT: "8080"
WEBDAV_PORT: "8081"

# Auth mode: "paperless" or "oidc"
AUTH_MODE: paperless

# If AUTH_MODE=oidc
OIDC_ISSUER: https://auth.example.com
OIDC_CLIENT_ID: paperless-webdav
OIDC_CLIENT_SECRET: <secret>
LDAP_URL: ldap://auth.example.com:389
LDAP_BASE_DN: dc=example,dc=com
LDAP_BIND_DN: cn=service,dc=example,dc=com  # optional, for search
LDAP_BIND_PASSWORD: <secret>                 # optional, for search

# Security
SESSION_EXPIRY_HOURS: "24"
RATE_LIMIT_ATTEMPTS: "5"
RATE_LIMIT_WINDOW_MINUTES: "15"

# Logging
LOG_LEVEL: INFO
LOG_FORMAT: json
```

### Kubernetes Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: paperless-webdav
spec:
  replicas: 1
  selector:
    matchLabels:
      app: paperless-webdav
  template:
    metadata:
      labels:
        app: paperless-webdav
    spec:
      securityContext:
        runAsNonRoot: true
        runAsUser: 1000
        fsGroup: 1000
      containers:
        - name: paperless-webdav
          image: ghcr.io/yourrepo/paperless-webdav:latest
          ports:
            - name: admin
              containerPort: 8080
            - name: webdav
              containerPort: 8081
          envFrom:
            - configMapRef:
                name: paperless-webdav-config
            - secretRef:
                name: paperless-webdav-secrets
          securityContext:
            readOnlyRootFilesystem: true
            allowPrivilegeEscalation: false
          volumeMounts:
            - name: tmp
              mountPath: /tmp
          resources:
            requests:
              memory: "128Mi"
              cpu: "100m"
            limits:
              memory: "512Mi"
              cpu: "500m"
          livenessProbe:
            httpGet:
              path: /health
              port: admin
            initialDelaySeconds: 10
            periodSeconds: 30
          readinessProbe:
            httpGet:
              path: /ready
              port: admin
            initialDelaySeconds: 5
            periodSeconds: 10
      volumes:
        - name: tmp
          emptyDir: {}
---
apiVersion: v1
kind: Service
metadata:
  name: paperless-webdav
spec:
  selector:
    app: paperless-webdav
  ports:
    - name: admin
      port: 8080
      targetPort: admin
    - name: webdav
      port: 8081
      targetPort: webdav
---
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: paperless-webdav
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt
spec:
  tls:
    - hosts:
        - webdav.example.com
        - webdav-admin.example.com
      secretName: paperless-webdav-tls
  rules:
    - host: webdav-admin.example.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: paperless-webdav
                port:
                  name: admin
    - host: webdav.example.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: paperless-webdav
                port:
                  name: webdav
```

## User Interface

### Admin UI Pages

1. **Login** - OIDC redirect or Paperless credentials form
2. **Token Setup** (OIDC only) - First-login prompt for Paperless API token
3. **Dashboard** - List of shares with status indicators
4. **Create/Edit Share** - Form with:
   - Share name input
   - Tag selector (autocomplete from Paperless)
   - Expiration date picker
   - Done folder toggle + name + tag selector
   - Allowed users input
5. **Share Details** - View share config, access stats, recent activity
6. **Settings** - Update Paperless token, view audit log

### UI Interactions (HTMX)

```html
<!-- Tag selector with autocomplete -->
<input type="text"
       name="tag-search"
       hx-get="/api/tags/search"
       hx-trigger="keyup changed delay:300ms"
       hx-target="#tag-suggestions"
       placeholder="Search tags...">
<div id="tag-suggestions"></div>

<!-- Share list with live status -->
<div hx-get="/api/shares"
     hx-trigger="load, every 30s"
     hx-swap="innerHTML">
  <!-- Share cards rendered here -->
</div>

<!-- Delete with confirmation -->
<button hx-delete="/api/shares/tax2025"
        hx-confirm="Delete share 'tax2025'? This cannot be undone."
        hx-target="closest .share-card"
        hx-swap="outerHTML swap:1s">
  Delete
</button>
```

## API Endpoints

### Admin API (Port 8080)

```
Authentication:
POST   /auth/login          # Paperless mode: get session
GET    /auth/callback       # OIDC mode: handle callback
POST   /auth/logout         # End session
POST   /auth/token          # Update Paperless API token

Shares:
GET    /api/shares          # List user's shares
POST   /api/shares          # Create share
GET    /api/shares/{name}   # Get share details
PUT    /api/shares/{name}   # Update share
DELETE /api/shares/{name}   # Delete share

Tags:
GET    /api/tags            # List all Paperless tags
GET    /api/tags/search?q=  # Search tags (autocomplete)

Health:
GET    /health              # Liveness check
GET    /ready               # Readiness check (DB + Paperless connectivity)
```

### WebDAV Endpoints (Port 8081)

```
/{share-name}/                    # Share root
/{share-name}/{document}.pdf      # Document access
/{share-name}/{done-folder}/      # Done folder
/{share-name}/{done-folder}/{document}.pdf
```

Supported WebDAV methods:
- `OPTIONS` - Capability discovery
- `PROPFIND` - List directory / get file properties
- `GET` - Download document
- `HEAD` - Get document metadata
- `MOVE` - Move to done folder (within same share only)

Not supported (read-only default):
- `PUT`, `DELETE`, `MKCOL`, `COPY`, `PROPPATCH`, `LOCK`, `UNLOCK`

## Implementation Phases

### Phase 1: Core Functionality
- [ ] Project scaffolding (FastAPI + wsgidav)
- [ ] Database models and migrations
- [ ] Paperless API client
- [ ] Basic PaperlessProvider (list + download)
- [ ] Share CRUD API
- [ ] Paperless-native authentication

### Phase 2: Admin UI
- [ ] Jinja templates + Tailwind setup
- [ ] Login flow
- [ ] Share management pages
- [ ] Tag autocomplete
- [ ] HTMX interactions

### Phase 3: Done Folder Feature
- [ ] Done folder virtual directory
- [ ] Move operation → tag addition
- [ ] Filtered listings (exclude done from root)

### Phase 4: OIDC Support
- [ ] OIDC authentication flow
- [ ] LDAP integration for WebDAV auth
- [ ] Token storage and encryption
- [ ] First-login token prompt

### Phase 5: Production Hardening
- [ ] Structured JSON logging
- [ ] Rate limiting
- [ ] Audit log
- [ ] Health/readiness endpoints
- [ ] Kubernetes manifests
- [ ] Container image build

### Phase 6: Polish
- [ ] Share expiration enforcement
- [ ] Allowed users feature
- [ ] UI refinements
- [ ] Documentation

## Open Questions

1. **Document filenames**: Should we use the Paperless document title or original filename for the WebDAV listing? (Recommend: title, with fallback to original)

2. **Large shares**: If a tag filter matches thousands of documents, should we paginate the WebDAV listing or just return all? (Need to test wsgidav behavior)

3. **Concurrent access**: If two users access the same share simultaneously, each with different Paperless permissions, how do we handle? (Recommend: use accessing user's token, not share creator's)

## References

- [wsgidav Documentation](https://wsgidav.readthedocs.io/)
- [wsgidav Custom Providers](https://wsgidav.readthedocs.io/en/latest/user_guide_custom_providers.html)
- [Paperless-ngx REST API](https://docs.paperless-ngx.com/api/)
- [FastAPI Security (OAuth2)](https://fastapi.tiangolo.com/tutorial/security/)
- [HTMX Documentation](https://htmx.org/docs/)
- [Authlib Documentation](https://docs.authlib.org/)
