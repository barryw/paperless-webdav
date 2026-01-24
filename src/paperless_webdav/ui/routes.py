"""UI routes for admin interface."""

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Query, Request
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
from paperless_webdav.services.shares import get_share_by_name, get_user_shares

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
