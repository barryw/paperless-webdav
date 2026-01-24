"""UI routes for admin interface."""

from datetime import datetime
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Form, Query, Request, Response
from pydantic import ValidationError
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from paperless_webdav.auth.paperless import (
    AuthenticatedUser,
    _authenticate_with_paperless,
    _create_session,
    get_current_user_optional,
)
from paperless_webdav.config import Settings, get_settings
from paperless_webdav.dependencies import get_db_session
from paperless_webdav.logging import get_logger
from paperless_webdav.paperless_client import PaperlessClient
from paperless_webdav.schemas import ShareCreate, ShareUpdate
from paperless_webdav.services.shares import (
    create_share,
    delete_share,
    get_share_by_name,
    get_user_shares,
    update_share,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/ui", tags=["ui"])

# Set up Jinja2 templates
templates_dir = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(templates_dir))


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request) -> HTMLResponse:
    """Render the login page."""
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={"error": None},
    )


@router.post("/login", response_model=None)
async def login_submit(
    request: Request,
    username: Annotated[str, Form()],
    password: Annotated[str, Form()],
    settings: Annotated[Settings, Depends(get_settings)],
) -> RedirectResponse | HTMLResponse:
    """Handle login form submission.

    Validates credentials against Paperless API and creates session on success.
    """
    token, error = await _authenticate_with_paperless(username, password, settings.paperless_url)

    if error is not None:
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={"error": error},
        )

    # Create session and redirect
    session_value = _create_session(username, token, settings)
    response = RedirectResponse(url="/ui/shares", status_code=303)
    response.set_cookie(
        key="session",
        value=session_value,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        max_age=settings.session_expiry_hours * 3600,
    )

    logger.info("login_success", username=username)
    return response


@router.get("/shares", response_class=HTMLResponse, response_model=None)
async def shares_list(
    request: Request,
    current_user: Annotated[AuthenticatedUser | None, Depends(get_current_user_optional)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> HTMLResponse | RedirectResponse:
    """Render the shares list page.

    Requires authentication - redirects to login if not authenticated.
    """
    if current_user is None:
        return RedirectResponse(url="/ui/login", status_code=303)

    shares = await get_user_shares(session, current_user.username)

    return templates.TemplateResponse(
        request=request,
        name="shares/list.html",
        context={"shares": shares, "username": current_user.username},
    )


@router.get("/shares/new", response_class=HTMLResponse, response_model=None)
async def create_share_page(
    request: Request,
    current_user: Annotated[AuthenticatedUser | None, Depends(get_current_user_optional)],
) -> HTMLResponse | RedirectResponse:
    """Render the create share form.

    Requires authentication - redirects to login if not authenticated.
    """
    if current_user is None:
        return RedirectResponse(url="/ui/login", status_code=303)

    return templates.TemplateResponse(
        request=request,
        name="shares/form.html",
        context={"share": None, "username": current_user.username},
    )


async def parse_share_form_data(request: Request) -> dict[str, Any]:
    """Parse form data from share create/edit form.

    Handles multi-value fields (getlist for tags and users),
    checkboxes (presence = true), and datetime-local inputs.

    Args:
        request: The FastAPI request object.

    Returns:
        Dictionary with parsed form data.
    """
    form = await request.form()

    # Parse multi-value fields
    include_tags = form.getlist("include_tags")
    exclude_tags = form.getlist("exclude_tags")
    allowed_users = form.getlist("allowed_users")

    # Parse checkboxes (presence = true)
    read_only = "read_only" in form
    done_folder_enabled = "done_folder_enabled" in form

    # Parse datetime-local input
    expires_at_value = form.get("expires_at", "")
    expires_at_str = str(expires_at_value) if expires_at_value else ""
    expires_at = None
    if expires_at_str:
        try:
            expires_at = datetime.fromisoformat(expires_at_str)
        except ValueError:
            pass  # Invalid datetime, leave as None

    # Get simple string fields
    name = form.get("name", "")
    done_folder_name = form.get("done_folder_name", "done") or "done"

    # done_tag is a single-select field but comes from hidden input
    done_tag_values = form.getlist("done_tag")
    done_tag = done_tag_values[0] if done_tag_values else None

    return {
        "name": name,
        "include_tags": include_tags,
        "exclude_tags": exclude_tags,
        "read_only": read_only,
        "done_folder_enabled": done_folder_enabled,
        "done_folder_name": done_folder_name,
        "done_tag": done_tag,
        "expires_at": expires_at,
        "allowed_users": allowed_users,
    }


def format_validation_error(error: ValidationError) -> str:
    """Format Pydantic validation error for display.

    Args:
        error: The Pydantic ValidationError.

    Returns:
        Human-readable error message.
    """
    messages = []
    for err in error.errors():
        field = ".".join(str(loc) for loc in err["loc"])
        msg = err["msg"]
        messages.append(f"{field}: {msg}")
    return "; ".join(messages)


@router.post("/shares/new", response_model=None)
async def create_share_submit(
    request: Request,
    current_user: Annotated[AuthenticatedUser | None, Depends(get_current_user_optional)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> HTMLResponse | RedirectResponse:
    """Handle create share form submission.

    Requires authentication - redirects to login if not authenticated.
    Creates a new share in the database.
    On success, redirects to shares list.
    On validation error, re-renders form with error message.
    """
    if current_user is None:
        return RedirectResponse(url="/ui/login", status_code=303)

    form_data = await parse_share_form_data(request)

    try:
        share_data = ShareCreate(**form_data)
    except ValidationError as e:
        error_msg = format_validation_error(e)
        logger.warning("share_create_validation_error", error=error_msg)
        return templates.TemplateResponse(
            request=request,
            name="shares/form.html",
            context={
                "share": None,
                "username": current_user.username,
                "error": error_msg,
            },
        )

    try:
        await create_share(session, current_user.username, share_data)
        logger.info("share_created_via_ui", share_name=share_data.name, user=current_user.username)
        return RedirectResponse(url="/ui/shares", status_code=303)
    except Exception as e:
        logger.error("share_create_error", error=str(e))
        return templates.TemplateResponse(
            request=request,
            name="shares/form.html",
            context={
                "share": None,
                "username": current_user.username,
                "error": f"Failed to create share: {e!s}",
            },
        )


@router.post("/shares/{name}/edit", response_model=None)
async def edit_share_submit(
    request: Request,
    name: str,
    current_user: Annotated[AuthenticatedUser | None, Depends(get_current_user_optional)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> HTMLResponse | RedirectResponse:
    """Handle edit share form submission.

    Requires authentication - redirects to login if not authenticated.
    Returns 404 if share not found or not accessible.
    Updates the share in the database.
    On success, redirects to shares list.
    On validation error, re-renders form with error message.
    """
    if current_user is None:
        return RedirectResponse(url="/ui/login", status_code=303)

    share = await get_share_by_name(session, name, current_user.username)

    if share is None:
        return RedirectResponse(url="/ui/shares", status_code=303)

    form_data = await parse_share_form_data(request)
    # Remove name from form_data for update (name cannot be changed)
    form_data.pop("name", None)

    try:
        share_update = ShareUpdate(**form_data)
    except ValidationError as e:
        error_msg = format_validation_error(e)
        logger.warning("share_update_validation_error", share_name=name, error=error_msg)
        return templates.TemplateResponse(
            request=request,
            name="shares/form.html",
            context={
                "share": share,
                "username": current_user.username,
                "error": error_msg,
            },
        )

    try:
        await update_share(session, share.id, share_update)
        logger.info("share_updated_via_ui", share_name=name, user=current_user.username)
        return RedirectResponse(url="/ui/shares", status_code=303)
    except Exception as e:
        logger.error("share_update_error", share_name=name, error=str(e))
        return templates.TemplateResponse(
            request=request,
            name="shares/form.html",
            context={
                "share": share,
                "username": current_user.username,
                "error": f"Failed to update share: {e!s}",
            },
        )


@router.get("/shares/{name}/edit", response_class=HTMLResponse, response_model=None)
async def edit_share_page(
    request: Request,
    name: str,
    current_user: Annotated[AuthenticatedUser | None, Depends(get_current_user_optional)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> HTMLResponse | RedirectResponse:
    """Render the edit share form.

    Requires authentication - redirects to login if not authenticated.
    Returns 404 if share not found or not accessible.
    """
    if current_user is None:
        return RedirectResponse(url="/ui/login", status_code=303)

    share = await get_share_by_name(session, name, current_user.username)

    if share is None:
        return RedirectResponse(url="/ui/shares", status_code=303)

    return templates.TemplateResponse(
        request=request,
        name="shares/form.html",
        context={"share": share, "username": current_user.username},
    )


@router.delete("/shares/{name}", response_model=None)
async def delete_share_handler(
    name: str,
    current_user: Annotated[AuthenticatedUser | None, Depends(get_current_user_optional)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> HTMLResponse:
    """Delete a share via HTMX.

    Requires authentication - returns 404 if not authenticated.
    Returns empty response on success (HTMX will remove the row).
    Returns 404 if share not found or not authorized.
    """
    if current_user is None:
        return HTMLResponse(content="", status_code=404)

    deleted = await delete_share(session, name, current_user.username)

    if not deleted:
        return HTMLResponse(content="", status_code=404)

    logger.info("share_deleted_via_ui", share_name=name, user=current_user.username)
    return HTMLResponse(content="", status_code=200)


@router.get("/partials/tag-suggestions", response_class=HTMLResponse, response_model=None)
async def tag_suggestions(
    request: Request,
    q: Annotated[str, Query(description="Tag name search query")] = "",
    field: Annotated[str, Query(description="Target field name")] = "include_tags",
    current_user: Annotated[AuthenticatedUser | None, Depends(get_current_user_optional)] = None,
    settings: Annotated[Settings, Depends(get_settings)] = None,
) -> HTMLResponse | RedirectResponse:
    """Return tag suggestions as HTML partial for HTMX autocomplete.

    Requires authentication - returns 401 if not authenticated.
    Searches Paperless for tags matching the query string.
    """
    if current_user is None:
        return HTMLResponse(content="", status_code=401)

    # Single-select fields
    single_fields = {"done_tag"}
    is_single = field in single_fields

    tags = []
    if q and len(q) >= 1:
        client = PaperlessClient(base_url=settings.paperless_url, token=current_user.token)
        tags = await client.search_tags(q)
        logger.debug("tag_suggestions_fetched", query=q, field=field, count=len(tags))

    return templates.TemplateResponse(
        request=request,
        name="partials/tag_suggestions.html",
        context={
            "tags": tags,
            "field": field,
            "single": is_single,
            "query": q,
        },
    )


@router.post("/logout", response_model=None)
async def logout(
    settings: Annotated[Settings, Depends(get_settings)],
) -> RedirectResponse:
    """Log out the user by clearing the session cookie.

    Clears the session cookie and redirects to login page.
    """
    response = RedirectResponse(url="/ui/login", status_code=303)
    response.set_cookie(
        key="session",
        value="",
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        max_age=0,
    )
    logger.info("user_logged_out")
    return response


@router.get("/token-setup", response_class=HTMLResponse, response_model=None)
async def token_setup_page(
    request: Request,
    current_user: Annotated[AuthenticatedUser | None, Depends(get_current_user_optional)],
) -> HTMLResponse | RedirectResponse:
    """Render the token setup page.

    Requires authentication - redirects to login if not authenticated.
    This page allows OIDC users to enter their Paperless API token.
    """
    if current_user is None:
        return RedirectResponse(url="/ui/login", status_code=303)

    return templates.TemplateResponse(
        request=request,
        name="token_setup.html",
        context={"error": None},
    )


@router.post("/token-setup", response_model=None)
async def token_setup_submit(
    request: Request,
    token: Annotated[str, Form()] = "",
    current_user: Annotated[AuthenticatedUser | None, Depends(get_current_user_optional)] = None,
    settings: Annotated[Settings, Depends(get_settings)] = None,
) -> HTMLResponse | RedirectResponse:
    """Handle token setup form submission.

    Validates the provided Paperless API token and updates the session.
    """
    if current_user is None:
        return RedirectResponse(url="/ui/login", status_code=303)

    # Check for empty token
    if not token or not token.strip():
        return templates.TemplateResponse(
            request=request,
            name="token_setup.html",
            context={"error": "Please enter your API token"},
        )

    # Validate the token against Paperless
    try:
        client = PaperlessClient(base_url=settings.paperless_url, token=token)
        is_valid = await client.validate_token()
    except Exception as e:
        logger.error("token_validation_error", error=str(e))
        return templates.TemplateResponse(
            request=request,
            name="token_setup.html",
            context={"error": "Failed to connect to Paperless server"},
        )

    if not is_valid:
        return templates.TemplateResponse(
            request=request,
            name="token_setup.html",
            context={"error": "Invalid API token"},
        )

    # Token is valid - create new session with the token
    session_value = _create_session(current_user.username, token, settings)
    response = RedirectResponse(url="/ui/shares", status_code=303)
    response.set_cookie(
        key="session",
        value=session_value,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        max_age=settings.session_expiry_hours * 3600,
    )

    logger.info("token_setup_success", username=current_user.username)
    return response


@router.get("/partials/user-suggestions", response_class=HTMLResponse, response_model=None)
async def user_suggestions(
    request: Request,
    q: Annotated[str, Query(description="Username search query")] = "",
    current_user: Annotated[AuthenticatedUser | None, Depends(get_current_user_optional)] = None,
    settings: Annotated[Settings, Depends(get_settings)] = None,
) -> HTMLResponse | RedirectResponse:
    """Return user suggestions as HTML partial for HTMX autocomplete.

    Requires authentication - returns 401 if not authenticated.
    Searches Paperless for users matching the query string.
    If user lacks permission (403), returns fallback message.
    """
    if current_user is None:
        return HTMLResponse(content="", status_code=401)

    users = []
    fallback = False

    if q and len(q) >= 1:
        client = PaperlessClient(base_url=settings.paperless_url, token=current_user.token)
        users = await client.search_users(q)
        # If we get no users and had a query, check if it's because of permissions
        if not users:
            # Try to determine if it's a permission issue by checking get_users
            all_users = await client.get_users()
            if not all_users:
                # Empty list from get_users means either no users or no permission
                # We assume permission issue if user searched but got nothing
                fallback = True
        logger.debug("user_suggestions_fetched", query=q, count=len(users), fallback=fallback)

    return templates.TemplateResponse(
        request=request,
        name="partials/user_suggestions.html",
        context={
            "users": users,
            "query": q,
            "fallback": fallback,
        },
    )
