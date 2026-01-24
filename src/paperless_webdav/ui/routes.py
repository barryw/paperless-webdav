"""UI routes for admin interface."""

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from paperless_webdav.auth.paperless import (
    _authenticate_with_paperless,
    _create_session,
)
from paperless_webdav.config import Settings, get_settings
from paperless_webdav.logging import get_logger

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
    token, error = await _authenticate_with_paperless(
        username, password, settings.paperless_url
    )

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
