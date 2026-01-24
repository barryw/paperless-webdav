# tests/test_services_shares.py
"""Integration tests for share service with database.

These tests use mocked database sessions to avoid requiring PostgreSQL
(which supports JSONB) for unit testing. Integration tests with a real
database should be run separately in CI with a PostgreSQL instance.
"""

import pytest
from datetime import datetime, timezone, timedelta
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy.ext.asyncio import AsyncSession

from paperless_webdav.models import User, Share
from paperless_webdav.schemas import ShareCreate, ShareUpdate


@pytest.fixture
def mock_session():
    """Create a mock async session for testing."""
    session = MagicMock(spec=AsyncSession)
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.add = MagicMock()
    session.delete = AsyncMock()
    return session


@pytest.fixture
def test_user():
    """Create a test user model instance."""
    return User(id=uuid4(), external_id="testuser")


@pytest.fixture
def other_user():
    """Create another test user model instance."""
    return User(id=uuid4(), external_id="otheruser")


def mock_result_with_value(value):
    """Create a mock result with scalar_one_or_none returning value."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def mock_result_with_scalars(values):
    """Create a mock result with scalars().all() returning values."""
    result = MagicMock()
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = values
    result.scalars.return_value = scalars_mock
    return result


class TestGetOrCreateUser:
    """Tests for get_or_create_user service function."""

    @pytest.mark.asyncio
    async def test_creates_user_if_not_exists(self, mock_session):
        """Should create new user when external_id not found."""
        from paperless_webdav.services.shares import get_or_create_user

        # Simulate no user found
        mock_session.execute.return_value = mock_result_with_value(None)

        user = await get_or_create_user(mock_session, "newuser")

        assert user is not None
        assert user.external_id == "newuser"
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_existing_user(self, mock_session, test_user):
        """Should return existing user when external_id found."""
        from paperless_webdav.services.shares import get_or_create_user

        # Simulate user found
        mock_session.execute.return_value = mock_result_with_value(test_user)

        user = await get_or_create_user(mock_session, test_user.external_id)

        assert user.id == test_user.id
        assert user.external_id == test_user.external_id
        mock_session.add.assert_not_called()


class TestGetUserShares:
    """Tests for get_user_shares service function."""

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_shares(self, mock_session):
        """Should return empty list when user has no shares."""
        from paperless_webdav.services.shares import get_user_shares

        # First call: user lookup returns None (no user)
        # Second call: shares query returns empty list
        mock_session.execute.side_effect = [
            mock_result_with_value(None),  # User not found
            mock_result_with_scalars([]),  # No shares
        ]

        shares = await get_user_shares(mock_session, "nonexistent")

        assert shares == []

    @pytest.mark.asyncio
    async def test_returns_owned_shares(self, mock_session, test_user):
        """Should return shares owned by the user."""
        from paperless_webdav.services.shares import get_user_shares

        share = Share(
            id=uuid4(),
            name="my-share",
            owner_id=test_user.id,
            include_tags=["tag1"],
        )

        mock_session.execute.side_effect = [
            mock_result_with_value(test_user),  # User found
            mock_result_with_scalars([share]),  # Share returned
        ]

        shares = await get_user_shares(mock_session, test_user.external_id)

        assert len(shares) == 1
        assert shares[0].name == "my-share"

    @pytest.mark.asyncio
    async def test_returns_shares_user_is_allowed_on(
        self, mock_session, test_user, other_user
    ):
        """Should return shares where user is in allowed_users list."""
        from paperless_webdav.services.shares import get_user_shares

        share = Share(
            id=uuid4(),
            name="shared-with-me",
            owner_id=other_user.id,
            include_tags=["tag1"],
            allowed_users=[test_user.external_id],
        )

        mock_session.execute.side_effect = [
            mock_result_with_value(test_user),  # User found
            mock_result_with_scalars([share]),  # Share returned
        ]

        shares = await get_user_shares(mock_session, test_user.external_id)

        assert len(shares) == 1
        assert shares[0].name == "shared-with-me"


class TestGetShareByName:
    """Tests for get_share_by_name service function."""

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self, mock_session):
        """Should return None when share doesn't exist."""
        from paperless_webdav.services.shares import get_share_by_name

        mock_session.execute.return_value = mock_result_with_value(None)

        share = await get_share_by_name(mock_session, "nonexistent", "anyuser")

        assert share is None

    @pytest.mark.asyncio
    async def test_returns_share_when_owner(self, mock_session, test_user):
        """Should return share when user is the owner."""
        from paperless_webdav.services.shares import get_share_by_name

        share = Share(
            id=uuid4(),
            name="my-share",
            owner_id=test_user.id,
            include_tags=["tag1"],
        )
        share._owner_external_id = test_user.external_id  # Mock joined data

        mock_session.execute.return_value = mock_result_with_value(share)

        # Mock the user lookup
        with patch(
            "paperless_webdav.services.shares._get_owner_external_id",
            new_callable=AsyncMock,
            return_value=test_user.external_id
        ):
            result = await get_share_by_name(mock_session, "my-share", test_user.external_id)

        assert result is not None
        assert result.name == "my-share"

    @pytest.mark.asyncio
    async def test_returns_share_when_allowed_user(
        self, mock_session, test_user, other_user
    ):
        """Should return share when user is in allowed_users."""
        from paperless_webdav.services.shares import get_share_by_name

        share = Share(
            id=uuid4(),
            name="shared-share",
            owner_id=other_user.id,
            include_tags=["tag1"],
            allowed_users=[test_user.external_id],
        )

        mock_session.execute.return_value = mock_result_with_value(share)

        with patch(
            "paperless_webdav.services.shares._get_owner_external_id",
            new_callable=AsyncMock,
            return_value=other_user.external_id
        ):
            result = await get_share_by_name(mock_session, "shared-share", test_user.external_id)

        assert result is not None
        assert result.name == "shared-share"

    @pytest.mark.asyncio
    async def test_returns_none_when_not_authorized(
        self, mock_session, test_user, other_user
    ):
        """Should return None when user is not authorized."""
        from paperless_webdav.services.shares import get_share_by_name

        share = Share(
            id=uuid4(),
            name="private-share",
            owner_id=other_user.id,
            include_tags=["tag1"],
            allowed_users=[],
        )

        mock_session.execute.return_value = mock_result_with_value(share)

        with patch(
            "paperless_webdav.services.shares._get_owner_external_id",
            new_callable=AsyncMock,
            return_value=other_user.external_id
        ):
            result = await get_share_by_name(mock_session, "private-share", test_user.external_id)

        assert result is None


class TestCreateShare:
    """Tests for create_share service function."""

    @pytest.mark.asyncio
    async def test_creates_share_with_minimum_fields(self, mock_session, test_user):
        """Should create share with required fields only."""
        from paperless_webdav.services.shares import create_share

        share_data = ShareCreate(name="new-share", include_tags=["tag1"])

        # Mock get_or_create_user to return test_user
        mock_session.execute.return_value = mock_result_with_value(test_user)

        share = await create_share(mock_session, test_user.external_id, share_data)

        assert share.name == "new-share"
        assert share.include_tags == ["tag1"]
        assert share.exclude_tags == []
        assert share.read_only is True
        assert share.done_folder_enabled is False
        mock_session.add.assert_called()

    @pytest.mark.asyncio
    async def test_creates_share_with_all_fields(self, mock_session, test_user):
        """Should create share with all optional fields."""
        from paperless_webdav.services.shares import create_share

        expires = datetime.now(timezone.utc) + timedelta(days=30)
        share_data = ShareCreate(
            name="full-share",
            include_tags=["tag1", "tag2"],
            exclude_tags=["draft"],
            expires_at=expires,
            read_only=False,
            done_folder_enabled=True,
            done_folder_name="completed",
            done_tag="done",
            allowed_users=["alice", "bob"],
        )

        mock_session.execute.return_value = mock_result_with_value(test_user)

        share = await create_share(mock_session, test_user.external_id, share_data)

        assert share.name == "full-share"
        assert share.include_tags == ["tag1", "tag2"]
        assert share.exclude_tags == ["draft"]
        assert share.read_only is False
        assert share.done_folder_enabled is True
        assert share.done_folder_name == "completed"
        assert share.done_tag == "done"
        assert share.allowed_users == ["alice", "bob"]


class TestUpdateShare:
    """Tests for update_share service function."""

    @pytest.mark.asyncio
    async def test_updates_include_tags(self, mock_session, test_user):
        """Should update include_tags field."""
        from paperless_webdav.services.shares import update_share

        share = Share(
            id=uuid4(),
            name="my-share",
            owner_id=test_user.id,
            include_tags=["old-tag"],
        )

        mock_session.execute.return_value = mock_result_with_value(share)

        share_data = ShareUpdate(include_tags=["new-tag1", "new-tag2"])
        updated = await update_share(mock_session, share.id, share_data)

        assert updated.include_tags == ["new-tag1", "new-tag2"]

    @pytest.mark.asyncio
    async def test_updates_multiple_fields(self, mock_session, test_user):
        """Should update multiple fields at once."""
        from paperless_webdav.services.shares import update_share

        share = Share(
            id=uuid4(),
            name="my-share",
            owner_id=test_user.id,
            include_tags=["tag1"],
            read_only=True,
        )

        mock_session.execute.return_value = mock_result_with_value(share)

        share_data = ShareUpdate(
            include_tags=["updated-tag"],
            exclude_tags=["exclude-this"],
            read_only=False,
        )
        updated = await update_share(mock_session, share.id, share_data)

        assert updated.include_tags == ["updated-tag"]
        assert updated.exclude_tags == ["exclude-this"]
        assert updated.read_only is False

    @pytest.mark.asyncio
    async def test_does_not_update_unset_fields(self, mock_session, test_user):
        """Should not modify fields that are not set in update."""
        from paperless_webdav.services.shares import update_share

        share = Share(
            id=uuid4(),
            name="my-share",
            owner_id=test_user.id,
            include_tags=["original"],
            exclude_tags=["keep-this"],
        )

        mock_session.execute.return_value = mock_result_with_value(share)

        share_data = ShareUpdate(include_tags=["updated"])
        updated = await update_share(mock_session, share.id, share_data)

        assert updated.include_tags == ["updated"]
        assert updated.exclude_tags == ["keep-this"]  # Unchanged

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self, mock_session):
        """Should return None when share not found."""
        from paperless_webdav.services.shares import update_share

        mock_session.execute.return_value = mock_result_with_value(None)

        share_data = ShareUpdate(include_tags=["tag"])
        result = await update_share(mock_session, uuid4(), share_data)

        assert result is None


class TestDeleteShare:
    """Tests for delete_share service function."""

    @pytest.mark.asyncio
    async def test_deletes_owned_share(self, mock_session, test_user):
        """Should delete share owned by user."""
        from paperless_webdav.services.shares import delete_share

        share = Share(
            id=uuid4(),
            name="my-share",
            owner_id=test_user.id,
            include_tags=["tag1"],
        )

        # First call: user lookup
        # Second call: share lookup
        mock_session.execute.side_effect = [
            mock_result_with_value(test_user),  # User found
            mock_result_with_value(share),  # Share found
        ]

        result = await delete_share(mock_session, "my-share", test_user.external_id)

        assert result is True
        mock_session.delete.assert_called_once_with(share)
        mock_session.commit.assert_called()

    @pytest.mark.asyncio
    async def test_returns_false_when_not_found(self, mock_session, test_user):
        """Should return False when share doesn't exist."""
        from paperless_webdav.services.shares import delete_share

        mock_session.execute.side_effect = [
            mock_result_with_value(test_user),  # User found
            mock_result_with_value(None),  # Share not found
        ]

        result = await delete_share(mock_session, "nonexistent", test_user.external_id)

        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_when_not_owner(
        self, mock_session, test_user, other_user
    ):
        """Should return False when user is not the owner."""
        from paperless_webdav.services.shares import delete_share

        share = Share(
            id=uuid4(),
            name="not-my-share",
            owner_id=other_user.id,
            include_tags=["tag1"],
            allowed_users=[test_user.external_id],  # Has access but not owner
        )

        mock_session.execute.side_effect = [
            mock_result_with_value(test_user),  # User found
            mock_result_with_value(share),  # Share found (but wrong owner)
        ]

        result = await delete_share(mock_session, "not-my-share", test_user.external_id)

        assert result is False
        mock_session.delete.assert_not_called()


class TestCheckDbConnectivity:
    """Tests for check_db_connectivity function."""

    @pytest.mark.asyncio
    async def test_returns_true_when_connected(self, mock_session):
        """Should return True when database is accessible."""
        from paperless_webdav.services.shares import check_db_connectivity

        mock_session.execute.return_value = MagicMock()

        result = await check_db_connectivity(mock_session)

        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_on_error(self):
        """Should return False when database query fails."""
        from paperless_webdav.services.shares import check_db_connectivity

        # Create a mock session that raises an error
        mock_session = MagicMock(spec=AsyncSession)
        mock_session.execute = AsyncMock(side_effect=Exception("Connection failed"))

        result = await check_db_connectivity(mock_session)

        assert result is False


class TestStoreUserToken:
    """Tests for store_user_token service function."""

    @pytest.mark.asyncio
    async def test_store_user_token_encrypts_token(self, mock_session, test_user):
        """store_user_token should encrypt the token before storing."""
        from paperless_webdav.services.shares import store_user_token

        # Mock user lookup - user exists
        mock_session.execute.return_value = mock_result_with_value(test_user)

        encryption_key = "MDEyMzQ1Njc4OTAxMjM0NTY3ODkwMTIzNDU2Nzg5MDE="  # 32 bytes base64

        with patch("paperless_webdav.services.shares.TokenEncryption") as mock_enc_class:
            mock_enc = MagicMock()
            mock_enc.encrypt.return_value = b"encrypted_token_data"
            mock_enc_class.return_value = mock_enc

            await store_user_token(
                mock_session, "testuser", "plain_token_123", encryption_key
            )

            # Verify TokenEncryption was initialized with key
            mock_enc_class.assert_called_once_with(encryption_key)
            # Verify encrypt was called with the plain token
            mock_enc.encrypt.assert_called_once_with("plain_token_123")

    @pytest.mark.asyncio
    async def test_store_user_token_creates_user_if_not_exists(self, mock_session):
        """store_user_token should create user if not exists."""
        from paperless_webdav.services.shares import store_user_token

        # First call: user not found, second call: after creation
        new_user = User(id=uuid4(), external_id="newuser")
        mock_session.execute.return_value = mock_result_with_value(None)

        encryption_key = "MDEyMzQ1Njc4OTAxMjM0NTY3ODkwMTIzNDU2Nzg5MDE="

        with patch("paperless_webdav.services.shares.TokenEncryption") as mock_enc_class:
            mock_enc = MagicMock()
            mock_enc.encrypt.return_value = b"encrypted_data"
            mock_enc_class.return_value = mock_enc

            await store_user_token(
                mock_session, "newuser", "token", encryption_key
            )

            # Verify a new user was added
            mock_session.add.assert_called()
            mock_session.commit.assert_called()

    @pytest.mark.asyncio
    async def test_store_user_token_updates_existing_user(self, mock_session, test_user):
        """store_user_token should update existing user's token."""
        from paperless_webdav.services.shares import store_user_token

        # User exists
        mock_session.execute.return_value = mock_result_with_value(test_user)

        encryption_key = "MDEyMzQ1Njc4OTAxMjM0NTY3ODkwMTIzNDU2Nzg5MDE="

        with patch("paperless_webdav.services.shares.TokenEncryption") as mock_enc_class:
            mock_enc = MagicMock()
            mock_enc.encrypt.return_value = b"new_encrypted_data"
            mock_enc_class.return_value = mock_enc

            await store_user_token(
                mock_session, test_user.external_id, "new_token", encryption_key
            )

            # Verify the user's token was updated
            assert test_user.paperless_token_encrypted == b"new_encrypted_data"
            mock_session.commit.assert_called()


class TestGetUserToken:
    """Tests for get_user_token service function."""

    @pytest.mark.asyncio
    async def test_get_user_token_decrypts_token(self, mock_session, test_user):
        """get_user_token should decrypt the stored token."""
        from paperless_webdav.services.shares import get_user_token

        # User has encrypted token
        test_user.paperless_token_encrypted = b"encrypted_token_data"
        mock_session.execute.return_value = mock_result_with_value(test_user)

        encryption_key = "MDEyMzQ1Njc4OTAxMjM0NTY3ODkwMTIzNDU2Nzg5MDE="

        with patch("paperless_webdav.services.shares.TokenEncryption") as mock_enc_class:
            mock_enc = MagicMock()
            mock_enc.decrypt.return_value = "decrypted_plain_token"
            mock_enc_class.return_value = mock_enc

            result = await get_user_token(
                mock_session, test_user.external_id, encryption_key
            )

            # Verify TokenEncryption was initialized with key
            mock_enc_class.assert_called_once_with(encryption_key)
            # Verify decrypt was called with the encrypted data
            mock_enc.decrypt.assert_called_once_with(b"encrypted_token_data")
            assert result == "decrypted_plain_token"

    @pytest.mark.asyncio
    async def test_get_user_token_returns_none_for_nonexistent_user(self, mock_session):
        """get_user_token should return None for non-existent user."""
        from paperless_webdav.services.shares import get_user_token

        # User not found
        mock_session.execute.return_value = mock_result_with_value(None)

        encryption_key = "MDEyMzQ1Njc4OTAxMjM0NTY3ODkwMTIzNDU2Nzg5MDE="

        result = await get_user_token(mock_session, "nonexistent", encryption_key)

        assert result is None

    @pytest.mark.asyncio
    async def test_get_user_token_returns_none_for_user_without_token(
        self, mock_session, test_user
    ):
        """get_user_token should return None for user without stored token."""
        from paperless_webdav.services.shares import get_user_token

        # User exists but has no token
        test_user.paperless_token_encrypted = None
        mock_session.execute.return_value = mock_result_with_value(test_user)

        encryption_key = "MDEyMzQ1Njc4OTAxMjM0NTY3ODkwMTIzNDU2Nzg5MDE="

        result = await get_user_token(mock_session, test_user.external_id, encryption_key)

        assert result is None
