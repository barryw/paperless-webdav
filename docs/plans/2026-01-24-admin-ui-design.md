# Admin UI Design

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:writing-plans to create detailed implementation tasks, then superpowers:subagent-driven-development to execute.

**Goal:** Build a web UI for users to manage their Paperless-ngx WebDAV shares.

**Stack:** Jinja2 templates + HTMX for dynamic interactions, Tailwind CSS via CDN.

---

## Routes

| Route | Purpose |
|-------|---------|
| `/ui/login` | Login form (Paperless auth) |
| `/ui/token-setup` | API token entry (OIDC users only) |
| `/ui/shares` | List user's shares (dashboard) |
| `/ui/shares/new` | Create share form |
| `/ui/shares/{name}/edit` | Edit share form |
| `/ui/partials/tag-suggestions` | HTMX partial for tag autocomplete |
| `/ui/partials/user-suggestions` | HTMX partial for user autocomplete |

## Authentication Flows

### Paperless Mode (`auth_mode=paperless`)
1. `/ui/login` shows username/password form
2. Submit calls `/api/auth/login` endpoint
3. Paperless validates credentials and returns API token automatically
4. Token stored encrypted in session, redirect to `/ui/shares`

### OIDC Mode (`auth_mode=oidc`)
1. `/ui/login` shows "Login with SSO" button
2. Redirects to OIDC provider, user authenticates
3. Callback returns user identity but no Paperless token
4. Redirect to `/ui/token-setup` - form asking for Paperless API token
5. User pastes their token (with instructions on where to find it in Paperless)
6. Token validated against Paperless API, stored encrypted, redirect to `/ui/shares`

If OIDC user returns with stored token, skip token-setup step.

## Share List Page (`/ui/shares`)

- Table columns: Name, Include Tags (colored pills), Expires, Actions
- Actions: Edit button, Delete button
- Delete triggers HTMX confirmation, removes row on success
- "Create Share" button at top
- Empty state message when no shares exist

## Create/Edit Form

**Fields:**
- **Name** - Text input (create only, disabled on edit)
- **Include Tags** - Autocomplete with chips (required, at least one)
- **Exclude Tags** - Autocomplete with chips (optional)
- **Done Folder** - Checkbox to enable, reveals:
  - Folder name input (default "done")
  - Done Tag autocomplete (single tag, required when enabled)
- **Read Only** - Checkbox (default checked)
- **Expires** - Optional datetime picker
- **Allowed Users** - Autocomplete with chips if user has permission to list users, otherwise text input fallback

**Actions:**
- Save button submits form, redirects to list on success
- Cancel button returns to list
- Validation errors shown inline

## Tag Autocomplete Component

**How it works:**
1. Text input with `hx-get="/ui/partials/tag-suggestions?q={value}"` on keyup (300ms debounce)
2. Server queries Paperless API for matching tags
3. Returns HTML partial with clickable tag items (name + color)
4. Click adds chip below input, clears input
5. Each chip has X button to remove
6. Hidden inputs sync values for form submission

**Modes:**
- Include/Exclude Tags: multi-select (array of chips)
- Done Tag: single-select (one chip max)

## User Autocomplete Component

**How it works:**
- Same pattern as tags, but fetches from Paperless `/api/users/` endpoint
- If user lacks permission (403), falls back to text input with comma-separated usernames
- Fallback shows helper text explaining manual entry

## Error Handling

**Form validation:**
- Server-side validation via existing Pydantic schemas
- Errors displayed inline next to relevant fields
- HTMX swaps error messages without full page reload

**Auth errors:**
- Session expired: redirect to login with flash message
- Invalid Paperless token (OIDC): show error, let user retry

**API failures:**
- Paperless unreachable during tag search: "Unable to load tags" in dropdown
- Save fails: error banner at top of form, preserve user input

**Permission errors:**
- Edit/delete non-owned share: 403, "Not authorized" message
- Share not found: 404, redirect to list with flash

**Flash messages:**
- Success: "Share created", "Share deleted"
- Errors: "Failed to save", "Share not found"
- Displayed at top of page, dismissible

## Files to Create

```
src/paperless_webdav/
├── ui/
│   ├── __init__.py
│   ├── routes.py          # UI route handlers
│   └── templates/
│       ├── base.html      # Layout with Tailwind + HTMX
│       ├── login.html
│       ├── token_setup.html
│       └── shares/
│           ├── list.html
│           ├── form.html  # Shared create/edit form
│       └── partials/
│           ├── tag_suggestions.html
│           ├── user_suggestions.html
│           └── flash.html
```

## Dependencies

Add to existing paperless_client.py:
- `get_users()` - List users from Paperless (for allowed_users autocomplete)
- `search_users(query)` - Search users by name/username
