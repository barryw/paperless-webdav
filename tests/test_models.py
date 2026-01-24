# tests/test_models.py
"""Tests for database models."""

import pytest
from uuid import uuid4

from paperless_webdav.models import User, Share, AuditLog


def test_user_model_has_required_fields():
    """User model should have all required fields."""
    user = User(
        id=uuid4(),
        external_id="auth0|123",
        paperless_token_encrypted=b"encrypted",
    )
    assert user.external_id == "auth0|123"
    assert user.paperless_token_encrypted == b"encrypted"


def test_share_model_has_required_fields():
    """Share model should have all required fields."""
    user_id = uuid4()
    share = Share(
        id=uuid4(),
        name="tax2025",
        owner_id=user_id,
        include_tags=["tax", "2025"],
        exclude_tags=["draft"],
        done_folder_enabled=True,
        done_folder_name="completed",
        done_tag="reviewed",
    )
    assert share.name == "tax2025"
    assert share.include_tags == ["tax", "2025"]
    assert share.done_folder_enabled is True


def test_share_name_validation():
    """Share names must be alphanumeric with dashes only."""
    # Valid names
    Share(id=uuid4(), name="tax2025", owner_id=uuid4(), include_tags=["tax"])
    Share(id=uuid4(), name="my-share-name", owner_id=uuid4(), include_tags=["tag"])

    # Invalid names should raise
    with pytest.raises(ValueError):
        Share(id=uuid4(), name="invalid name", owner_id=uuid4(), include_tags=["tax"])
    with pytest.raises(ValueError):
        Share(id=uuid4(), name="invalid/path", owner_id=uuid4(), include_tags=["tax"])


def test_audit_log_model():
    """AuditLog model should capture security events."""
    log = AuditLog(
        id=uuid4(),
        event_type="document_accessed",
        user_id=uuid4(),
        share_id=uuid4(),
        ip_address="192.168.1.100",
        user_agent="Mozilla/5.0",
        details={"document_id": 123},
    )
    assert log.event_type == "document_accessed"
    assert log.details["document_id"] == 123
