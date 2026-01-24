# tests/test_webdav_provider.py
"""Tests for the WebDAV provider."""

from datetime import datetime
from io import BytesIO
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from paperless_webdav.paperless_client import PaperlessDocument, PaperlessTag
from paperless_webdav.webdav_provider import (
    DocumentResource,
    DoneFolderResource,
    PaperlessProvider,
    RootResource,
    ShareResource,
    sanitize_filename,
)


# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture
def mock_environ() -> dict[str, Any]:
    """Create a mock WSGI environ dict."""
    return {
        "REQUEST_METHOD": "GET",
        "PATH_INFO": "/",
        "wsgidav.provider": None,
    }


@pytest.fixture
def mock_share() -> MagicMock:
    """Create a mock Share object."""
    share = MagicMock()
    share.id = uuid4()
    share.name = "tax2025"
    share.include_tags = ["tax", "2025"]
    share.exclude_tags = ["draft"]
    share.read_only = True
    share.done_folder_enabled = False
    share.done_folder_name = "done"
    share.done_tag = "processed"
    return share


@pytest.fixture
def sample_document() -> PaperlessDocument:
    """Create a sample PaperlessDocument."""
    return PaperlessDocument(
        id=42,
        title="Tax Invoice 2025",
        original_file_name="tax-invoice-2025.pdf",
        created="2025-01-15T10:30:00Z",
        modified="2025-01-15T14:45:00Z",
        tags=[1, 2, 3],
    )


@pytest.fixture
def sample_documents() -> list[PaperlessDocument]:
    """Create a list of sample documents."""
    return [
        PaperlessDocument(
            id=1,
            title="Invoice 001",
            original_file_name="invoice-001.pdf",
            created="2025-01-10T09:00:00Z",
            modified="2025-01-10T09:00:00Z",
            tags=[1],
        ),
        PaperlessDocument(
            id=2,
            title="Receipt 002",
            original_file_name="receipt-002.pdf",
            created="2025-01-11T10:00:00Z",
            modified="2025-01-11T10:00:00Z",
            tags=[1, 2],
        ),
    ]


# -----------------------------------------------------------------------------
# sanitize_filename tests
# -----------------------------------------------------------------------------


class TestSanitizeFilename:
    """Tests for the sanitize_filename function."""

    def test_returns_normal_filename_unchanged(self) -> None:
        """Normal alphanumeric filenames should pass through."""
        assert sanitize_filename("invoice-2025") == "invoice-2025"
        assert sanitize_filename("Tax Document") == "Tax Document"

    def test_removes_path_separators(self) -> None:
        """Path separators (/ and \\) should be removed."""
        assert sanitize_filename("path/to/file") == "pathtofile"
        assert sanitize_filename("path\\to\\file") == "pathtofile"

    def test_removes_dangerous_characters(self) -> None:
        """Filesystem-unsafe characters should be removed."""
        # Remove: < > : " | ? *
        assert sanitize_filename('file<name>') == "filename"
        assert sanitize_filename('file:name') == "filename"
        assert sanitize_filename('file"name') == "filename"
        assert sanitize_filename('file|name') == "filename"
        assert sanitize_filename('file?name') == "filename"
        assert sanitize_filename('file*name') == "filename"

    def test_handles_empty_string(self) -> None:
        """Empty or all-unsafe strings should return a default name."""
        assert sanitize_filename("") == "untitled"
        assert sanitize_filename("///") == "untitled"
        assert sanitize_filename("<>:") == "untitled"

    def test_strips_whitespace(self) -> None:
        """Leading and trailing whitespace should be stripped."""
        assert sanitize_filename("  invoice  ") == "invoice"

    def test_preserves_unicode(self) -> None:
        """Unicode characters should be preserved."""
        assert sanitize_filename("Rechnung-2025") == "Rechnung-2025"
        assert sanitize_filename("facture-francaise") == "facture-francaise"


# -----------------------------------------------------------------------------
# PaperlessProvider tests
# -----------------------------------------------------------------------------


class TestPaperlessProvider:
    """Tests for the PaperlessProvider class."""

    def test_resolves_root_path(self, mock_environ: dict[str, Any]) -> None:
        """Provider should return RootResource for root path."""
        shares: dict[str, Any] = {}
        provider = PaperlessProvider(shares=shares)

        resource = provider.get_resource_inst("/", mock_environ)

        assert isinstance(resource, RootResource)

    def test_resolves_share_path(
        self, mock_environ: dict[str, Any], mock_share: MagicMock
    ) -> None:
        """Provider should return ShareResource for /{sharename}."""
        shares: dict[str, Any] = {"tax2025": mock_share}
        provider = PaperlessProvider(shares=shares)

        resource = provider.get_resource_inst("/tax2025", mock_environ)

        assert isinstance(resource, ShareResource)

    def test_returns_none_for_unknown_share(
        self, mock_environ: dict[str, Any]
    ) -> None:
        """Provider should return None for non-existent shares."""
        shares: dict[str, Any] = {}
        provider = PaperlessProvider(shares=shares)

        resource = provider.get_resource_inst("/nonexistent", mock_environ)

        assert resource is None

    def test_resolves_document_path(
        self,
        mock_environ: dict[str, Any],
        mock_share: MagicMock,
        sample_documents: list[PaperlessDocument],
    ) -> None:
        """Provider should return DocumentResource for /{share}/{doc}.pdf."""
        shares: dict[str, Any] = {"tax2025": mock_share}
        documents_by_share: dict[str, list[PaperlessDocument]] = {
            "tax2025": sample_documents
        }
        provider = PaperlessProvider(
            shares=shares, documents_by_share=documents_by_share
        )

        # Document filename is sanitized title + .pdf
        resource = provider.get_resource_inst(
            "/tax2025/Invoice 001.pdf", mock_environ
        )

        assert isinstance(resource, DocumentResource)

    def test_resolves_done_folder_path(
        self, mock_environ: dict[str, Any], mock_share: MagicMock
    ) -> None:
        """Provider should return DoneFolderResource for /{share}/done."""
        mock_share.done_folder_enabled = True
        shares: dict[str, Any] = {"tax2025": mock_share}
        provider = PaperlessProvider(shares=shares)

        resource = provider.get_resource_inst("/tax2025/done", mock_environ)

        assert isinstance(resource, DoneFolderResource)

    def test_done_folder_not_accessible_when_disabled(
        self, mock_environ: dict[str, Any], mock_share: MagicMock
    ) -> None:
        """Done folder should not be accessible when disabled."""
        mock_share.done_folder_enabled = False
        shares: dict[str, Any] = {"tax2025": mock_share}
        provider = PaperlessProvider(shares=shares)

        resource = provider.get_resource_inst("/tax2025/done", mock_environ)

        assert resource is None


# -----------------------------------------------------------------------------
# RootResource tests
# -----------------------------------------------------------------------------


class TestRootResource:
    """Tests for the RootResource class."""

    def test_get_member_names_lists_shares(
        self, mock_environ: dict[str, Any], mock_share: MagicMock
    ) -> None:
        """RootResource should list all available shares."""
        shares: dict[str, Any] = {
            "tax2025": mock_share,
            "invoices": MagicMock(name="invoices"),
        }
        provider = PaperlessProvider(shares=shares)

        root = RootResource("/", mock_environ, provider)
        member_names = root.get_member_names()

        assert set(member_names) == {"tax2025", "invoices"}

    def test_get_member_names_empty_when_no_shares(
        self, mock_environ: dict[str, Any]
    ) -> None:
        """RootResource should return empty list when no shares exist."""
        shares: dict[str, Any] = {}
        provider = PaperlessProvider(shares=shares)

        root = RootResource("/", mock_environ, provider)
        member_names = root.get_member_names()

        assert member_names == []

    def test_display_name_is_root(self, mock_environ: dict[str, Any]) -> None:
        """RootResource display name should indicate root."""
        shares: dict[str, Any] = {}
        provider = PaperlessProvider(shares=shares)

        root = RootResource("/", mock_environ, provider)

        # Default behavior returns last path segment or empty for root
        assert root.get_display_name() == ""


# -----------------------------------------------------------------------------
# ShareResource tests
# -----------------------------------------------------------------------------


class TestShareResource:
    """Tests for the ShareResource class."""

    def test_display_name_returns_share_name(
        self, mock_environ: dict[str, Any], mock_share: MagicMock
    ) -> None:
        """ShareResource display name should be the share name."""
        shares: dict[str, Any] = {"tax2025": mock_share}
        provider = PaperlessProvider(shares=shares)

        share_resource = ShareResource(
            "/tax2025", mock_environ, provider, mock_share
        )

        assert share_resource.get_display_name() == "tax2025"

    def test_get_member_names_lists_documents(
        self,
        mock_environ: dict[str, Any],
        mock_share: MagicMock,
        sample_documents: list[PaperlessDocument],
    ) -> None:
        """ShareResource should list document filenames."""
        shares: dict[str, Any] = {"tax2025": mock_share}
        documents_by_share: dict[str, list[PaperlessDocument]] = {
            "tax2025": sample_documents
        }
        provider = PaperlessProvider(
            shares=shares, documents_by_share=documents_by_share
        )

        share_resource = ShareResource(
            "/tax2025", mock_environ, provider, mock_share
        )
        member_names = share_resource.get_member_names()

        # Documents are listed as {title}.pdf
        assert "Invoice 001.pdf" in member_names
        assert "Receipt 002.pdf" in member_names

    def test_get_member_names_includes_done_folder_when_enabled(
        self, mock_environ: dict[str, Any], mock_share: MagicMock
    ) -> None:
        """ShareResource should include done folder when enabled."""
        mock_share.done_folder_enabled = True
        mock_share.done_folder_name = "completed"
        shares: dict[str, Any] = {"tax2025": mock_share}
        documents_by_share: dict[str, list[PaperlessDocument]] = {"tax2025": []}
        provider = PaperlessProvider(
            shares=shares, documents_by_share=documents_by_share
        )

        share_resource = ShareResource(
            "/tax2025", mock_environ, provider, mock_share
        )
        member_names = share_resource.get_member_names()

        assert "completed" in member_names


# -----------------------------------------------------------------------------
# DocumentResource tests
# -----------------------------------------------------------------------------


class TestDocumentResource:
    """Tests for the DocumentResource class."""

    def test_content_type_is_pdf(
        self,
        mock_environ: dict[str, Any],
        mock_share: MagicMock,
        sample_document: PaperlessDocument,
    ) -> None:
        """DocumentResource should report PDF content type."""
        shares: dict[str, Any] = {"tax2025": mock_share}
        provider = PaperlessProvider(shares=shares)

        doc_resource = DocumentResource(
            "/tax2025/Tax Invoice 2025.pdf",
            mock_environ,
            provider,
            sample_document,
        )

        assert doc_resource.get_content_type() == "application/pdf"

    def test_exposes_creation_date(
        self,
        mock_environ: dict[str, Any],
        mock_share: MagicMock,
        sample_document: PaperlessDocument,
    ) -> None:
        """DocumentResource should expose creation date."""
        shares: dict[str, Any] = {"tax2025": mock_share}
        provider = PaperlessProvider(shares=shares)

        doc_resource = DocumentResource(
            "/tax2025/Tax Invoice 2025.pdf",
            mock_environ,
            provider,
            sample_document,
        )

        creation_date = doc_resource.get_creation_date()
        assert creation_date is not None
        assert isinstance(creation_date, datetime)

    def test_exposes_last_modified(
        self,
        mock_environ: dict[str, Any],
        mock_share: MagicMock,
        sample_document: PaperlessDocument,
    ) -> None:
        """DocumentResource should expose last modified date."""
        shares: dict[str, Any] = {"tax2025": mock_share}
        provider = PaperlessProvider(shares=shares)

        doc_resource = DocumentResource(
            "/tax2025/Tax Invoice 2025.pdf",
            mock_environ,
            provider,
            sample_document,
        )

        modified = doc_resource.get_last_modified()
        assert modified is not None
        assert isinstance(modified, datetime)

    def test_exposes_etag(
        self,
        mock_environ: dict[str, Any],
        mock_share: MagicMock,
        sample_document: PaperlessDocument,
    ) -> None:
        """DocumentResource should expose an etag for caching."""
        shares: dict[str, Any] = {"tax2025": mock_share}
        provider = PaperlessProvider(shares=shares)

        doc_resource = DocumentResource(
            "/tax2025/Tax Invoice 2025.pdf",
            mock_environ,
            provider,
            sample_document,
        )

        etag = doc_resource.get_etag()
        assert etag is not None
        assert isinstance(etag, str)
        # Etag should include document id and modified time for cache invalidation
        assert "42" in etag or sample_document.modified in etag

    def test_display_name_is_sanitized_title(
        self,
        mock_environ: dict[str, Any],
        mock_share: MagicMock,
        sample_document: PaperlessDocument,
    ) -> None:
        """DocumentResource display name should be sanitized title + .pdf."""
        shares: dict[str, Any] = {"tax2025": mock_share}
        provider = PaperlessProvider(shares=shares)

        doc_resource = DocumentResource(
            "/tax2025/Tax Invoice 2025.pdf",
            mock_environ,
            provider,
            sample_document,
        )

        assert doc_resource.get_display_name() == "Tax Invoice 2025.pdf"


# -----------------------------------------------------------------------------
# Document filename sanitization integration
# -----------------------------------------------------------------------------


class TestDocumentFilenameSanitization:
    """Tests for document filename sanitization in the provider."""

    def test_document_with_unsafe_title_is_sanitized(
        self, mock_environ: dict[str, Any], mock_share: MagicMock
    ) -> None:
        """Documents with unsafe characters in title should be sanitized."""
        document = PaperlessDocument(
            id=99,
            title="Invoice: Jan/Feb <2025>",
            original_file_name="invoice.pdf",
            created="2025-01-01T00:00:00Z",
            modified="2025-01-01T00:00:00Z",
            tags=[],
        )
        shares: dict[str, Any] = {"tax2025": mock_share}
        documents_by_share: dict[str, list[PaperlessDocument]] = {
            "tax2025": [document]
        }
        provider = PaperlessProvider(
            shares=shares, documents_by_share=documents_by_share
        )

        share_resource = ShareResource(
            "/tax2025", mock_environ, provider, mock_share
        )
        member_names = share_resource.get_member_names()

        # Unsafe chars should be removed
        assert "Invoice JanFeb 2025.pdf" in member_names

    def test_provider_resolves_sanitized_filename(
        self, mock_environ: dict[str, Any], mock_share: MagicMock
    ) -> None:
        """Provider should resolve documents by their sanitized filename."""
        document = PaperlessDocument(
            id=99,
            title="Invoice: Jan/Feb <2025>",
            original_file_name="invoice.pdf",
            created="2025-01-01T00:00:00Z",
            modified="2025-01-01T00:00:00Z",
            tags=[],
        )
        shares: dict[str, Any] = {"tax2025": mock_share}
        documents_by_share: dict[str, list[PaperlessDocument]] = {
            "tax2025": [document]
        }
        provider = PaperlessProvider(
            shares=shares, documents_by_share=documents_by_share
        )

        resource = provider.get_resource_inst(
            "/tax2025/Invoice JanFeb 2025.pdf", mock_environ
        )

        assert isinstance(resource, DocumentResource)
        assert resource.document.id == 99


# -----------------------------------------------------------------------------
# DoneFolderResource tests
# -----------------------------------------------------------------------------


class TestDoneFolderResource:
    """Tests for the DoneFolderResource class."""

    def test_display_name_returns_folder_name(
        self, mock_environ: dict[str, Any], mock_share: MagicMock
    ) -> None:
        """DoneFolderResource display name should be the configured name."""
        mock_share.done_folder_name = "completed"
        shares: dict[str, Any] = {"tax2025": mock_share}
        provider = PaperlessProvider(shares=shares)

        done_folder = DoneFolderResource(
            "/tax2025/completed", mock_environ, provider, mock_share
        )

        assert done_folder.get_display_name() == "completed"

    def test_get_member_names_returns_empty(
        self, mock_environ: dict[str, Any], mock_share: MagicMock
    ) -> None:
        """DoneFolderResource should return empty list (placeholder)."""
        mock_share.done_folder_name = "done"
        shares: dict[str, Any] = {"tax2025": mock_share}
        provider = PaperlessProvider(shares=shares)

        done_folder = DoneFolderResource(
            "/tax2025/done", mock_environ, provider, mock_share
        )

        # Placeholder implementation returns empty
        assert done_folder.get_member_names() == []


# -----------------------------------------------------------------------------
# Dynamic Document Loading Tests
# -----------------------------------------------------------------------------


@pytest.fixture
def mock_paperless_client() -> AsyncMock:
    """Create a mock PaperlessClient."""
    client = AsyncMock()
    # Default tag lookup returns sample tags
    client.get_tags.return_value = [
        PaperlessTag(id=1, name="tax", slug="tax"),
        PaperlessTag(id=2, name="2025", slug="2025"),
        PaperlessTag(id=3, name="draft", slug="draft"),
        PaperlessTag(id=4, name="processed", slug="processed"),
    ]
    # Default document fetch returns empty list
    client.get_documents.return_value = []
    # Default download returns sample PDF bytes
    client.download_document.return_value = b"%PDF-1.4 sample content"
    return client


@pytest.fixture
def mock_environ_with_token() -> dict[str, Any]:
    """Create a mock WSGI environ dict with paperless token."""
    return {
        "REQUEST_METHOD": "GET",
        "PATH_INFO": "/",
        "wsgidav.provider": None,
        "paperless.token": "test-api-token-12345",
    }


class TestDynamicDocumentLoading:
    """Tests for dynamic document loading from Paperless API."""

    def test_provider_requires_paperless_url(self) -> None:
        """Provider should accept paperless_url for creating clients."""
        shares: dict[str, Any] = {}
        provider = PaperlessProvider(
            shares=shares,
            paperless_url="http://paperless.local",
        )
        assert provider._paperless_url == "http://paperless.local"

    def test_share_resource_loads_documents_from_client(
        self,
        mock_environ_with_token: dict[str, Any],
        mock_share: MagicMock,
        mock_paperless_client: AsyncMock,
        sample_documents: list[PaperlessDocument],
    ) -> None:
        """ShareResource should load documents via PaperlessClient."""
        mock_paperless_client.get_documents.return_value = sample_documents
        shares: dict[str, Any] = {"tax2025": mock_share}
        provider = PaperlessProvider(
            shares=shares,
            paperless_url="http://paperless.local",
        )

        with patch.object(
            provider, "_create_client", return_value=mock_paperless_client
        ):
            share_resource = ShareResource(
                "/tax2025", mock_environ_with_token, provider, mock_share
            )
            member_names = share_resource.get_member_names()

        # Should have loaded documents from client
        assert "Invoice 001.pdf" in member_names
        assert "Receipt 002.pdf" in member_names
        mock_paperless_client.get_documents.assert_called_once()

    def test_share_resource_resolves_tag_names_to_ids(
        self,
        mock_environ_with_token: dict[str, Any],
        mock_share: MagicMock,
        mock_paperless_client: AsyncMock,
    ) -> None:
        """ShareResource should resolve tag names to IDs for filtering."""
        # Share config uses tag names: include_tags=["tax", "2025"], exclude_tags=["draft"]
        mock_share.include_tags = ["tax", "2025"]
        mock_share.exclude_tags = ["draft"]
        mock_paperless_client.get_documents.return_value = []

        shares: dict[str, Any] = {"tax2025": mock_share}
        provider = PaperlessProvider(
            shares=shares,
            paperless_url="http://paperless.local",
        )

        with patch.object(
            provider, "_create_client", return_value=mock_paperless_client
        ):
            share_resource = ShareResource(
                "/tax2025", mock_environ_with_token, provider, mock_share
            )
            share_resource.get_member_names()

        # Should have called get_tags to resolve names to IDs
        mock_paperless_client.get_tags.assert_called()
        # Should have called get_documents with resolved tag IDs
        mock_paperless_client.get_documents.assert_called_once_with(
            include_tag_ids=[1, 2],  # "tax"=1, "2025"=2
            exclude_tag_ids=[3],  # "draft"=3
        )

    def test_share_resource_handles_missing_tags_gracefully(
        self,
        mock_environ_with_token: dict[str, Any],
        mock_share: MagicMock,
        mock_paperless_client: AsyncMock,
    ) -> None:
        """ShareResource should handle nonexistent tag names gracefully."""
        mock_share.include_tags = ["tax", "nonexistent-tag"]
        mock_share.exclude_tags = []
        mock_paperless_client.get_documents.return_value = []

        shares: dict[str, Any] = {"tax2025": mock_share}
        provider = PaperlessProvider(
            shares=shares,
            paperless_url="http://paperless.local",
        )

        with patch.object(
            provider, "_create_client", return_value=mock_paperless_client
        ):
            share_resource = ShareResource(
                "/tax2025", mock_environ_with_token, provider, mock_share
            )
            # Should not raise, even if tag doesn't exist
            share_resource.get_member_names()

        # Should only include valid tag IDs (tag "tax"=1 exists)
        mock_paperless_client.get_documents.assert_called_once()
        call_args = mock_paperless_client.get_documents.call_args
        assert 1 in call_args.kwargs.get("include_tag_ids", [])


class TestDocumentContentDownload:
    """Tests for document content download from Paperless API."""

    def test_document_get_content_downloads_from_client(
        self,
        mock_environ_with_token: dict[str, Any],
        mock_share: MagicMock,
        sample_document: PaperlessDocument,
        mock_paperless_client: AsyncMock,
    ) -> None:
        """DocumentResource.get_content() should download via client."""
        expected_content = b"%PDF-1.4 actual document content here..."
        mock_paperless_client.download_document.return_value = expected_content

        shares: dict[str, Any] = {"tax2025": mock_share}
        provider = PaperlessProvider(
            shares=shares,
            paperless_url="http://paperless.local",
        )

        with patch.object(
            provider, "_create_client", return_value=mock_paperless_client
        ):
            doc_resource = DocumentResource(
                "/tax2025/Tax Invoice 2025.pdf",
                mock_environ_with_token,
                provider,
                sample_document,
            )
            content_stream = doc_resource.get_content()

        # get_content returns a BytesIO stream
        assert content_stream.read() == expected_content
        mock_paperless_client.download_document.assert_called_once_with(
            sample_document.id
        )

    def test_document_get_content_returns_stream(
        self,
        mock_environ_with_token: dict[str, Any],
        mock_share: MagicMock,
        sample_document: PaperlessDocument,
        mock_paperless_client: AsyncMock,
    ) -> None:
        """DocumentResource.get_content() should return a file-like object."""
        expected_content = b"%PDF-1.4 stream content"
        mock_paperless_client.download_document.return_value = expected_content

        shares: dict[str, Any] = {"tax2025": mock_share}
        provider = PaperlessProvider(
            shares=shares,
            paperless_url="http://paperless.local",
        )

        with patch.object(
            provider, "_create_client", return_value=mock_paperless_client
        ):
            doc_resource = DocumentResource(
                "/tax2025/Tax Invoice 2025.pdf",
                mock_environ_with_token,
                provider,
                sample_document,
            )
            content = doc_resource.get_content()

        # wsgidav expects a file-like object or bytes
        # Check it's readable as bytes
        if isinstance(content, BytesIO):
            assert content.read() == expected_content
        else:
            assert content == expected_content

    def test_document_get_content_length_returns_actual_size(
        self,
        mock_environ_with_token: dict[str, Any],
        mock_share: MagicMock,
        sample_document: PaperlessDocument,
        mock_paperless_client: AsyncMock,
    ) -> None:
        """DocumentResource.get_content_length() should return actual size."""
        expected_content = b"%PDF-1.4 content of known size"
        mock_paperless_client.download_document.return_value = expected_content

        shares: dict[str, Any] = {"tax2025": mock_share}
        provider = PaperlessProvider(
            shares=shares,
            paperless_url="http://paperless.local",
        )

        with patch.object(
            provider, "_create_client", return_value=mock_paperless_client
        ):
            doc_resource = DocumentResource(
                "/tax2025/Tax Invoice 2025.pdf",
                mock_environ_with_token,
                provider,
                sample_document,
            )
            # First call to get_content to load the document
            doc_resource.get_content()
            # Then check length
            length = doc_resource.get_content_length()

        # Should be the actual size of downloaded content
        assert length == len(expected_content)


class TestClientCreation:
    """Tests for PaperlessClient creation from environ."""

    def test_provider_creates_client_from_environ_token(
        self,
        mock_environ_with_token: dict[str, Any],
        mock_share: MagicMock,
    ) -> None:
        """Provider should create client using token from environ."""
        shares: dict[str, Any] = {"tax2025": mock_share}
        provider = PaperlessProvider(
            shares=shares,
            paperless_url="http://paperless.local",
        )

        client = provider._create_client(mock_environ_with_token)

        assert client is not None
        assert client.base_url == "http://paperless.local"
        assert client.token == "test-api-token-12345"

    def test_provider_returns_none_without_token(
        self,
        mock_environ: dict[str, Any],
        mock_share: MagicMock,
    ) -> None:
        """Provider should return None if no token in environ."""
        shares: dict[str, Any] = {"tax2025": mock_share}
        provider = PaperlessProvider(
            shares=shares,
            paperless_url="http://paperless.local",
        )

        # mock_environ doesn't have paperless.token
        client = provider._create_client(mock_environ)

        assert client is None


class TestBackwardCompatibility:
    """Tests ensuring backward compatibility with static documents_by_share."""

    def test_provider_accepts_static_documents_by_share(
        self,
        mock_environ: dict[str, Any],
        mock_share: MagicMock,
        sample_documents: list[PaperlessDocument],
    ) -> None:
        """Provider should still accept documents_by_share for static mode."""
        shares: dict[str, Any] = {"tax2025": mock_share}
        documents_by_share: dict[str, list[PaperlessDocument]] = {
            "tax2025": sample_documents
        }

        # Should work without paperless_url
        provider = PaperlessProvider(
            shares=shares,
            documents_by_share=documents_by_share,
        )

        share_resource = ShareResource(
            "/tax2025", mock_environ, provider, mock_share
        )
        member_names = share_resource.get_member_names()

        assert "Invoice 001.pdf" in member_names
        assert "Receipt 002.pdf" in member_names

    def test_dynamic_loading_takes_precedence_over_static(
        self,
        mock_environ_with_token: dict[str, Any],
        mock_share: MagicMock,
        mock_paperless_client: AsyncMock,
        sample_documents: list[PaperlessDocument],
    ) -> None:
        """Dynamic loading should take precedence when client is available."""
        # Static documents
        static_doc = PaperlessDocument(
            id=999,
            title="Static Document",
            original_file_name="static.pdf",
            created="2025-01-01T00:00:00Z",
            modified="2025-01-01T00:00:00Z",
            tags=[],
        )
        # Dynamic documents from client
        mock_paperless_client.get_documents.return_value = sample_documents

        shares: dict[str, Any] = {"tax2025": mock_share}
        provider = PaperlessProvider(
            shares=shares,
            documents_by_share={"tax2025": [static_doc]},
            paperless_url="http://paperless.local",
        )

        with patch.object(
            provider, "_create_client", return_value=mock_paperless_client
        ):
            share_resource = ShareResource(
                "/tax2025", mock_environ_with_token, provider, mock_share
            )
            member_names = share_resource.get_member_names()

        # Should have dynamic documents, not static
        assert "Invoice 001.pdf" in member_names
        assert "Receipt 002.pdf" in member_names
        assert "Static Document.pdf" not in member_names


# -----------------------------------------------------------------------------
# Filename Collision Tests
# -----------------------------------------------------------------------------


class TestFilenameCollision:
    """Tests for filename collision handling."""

    def test_collision_logs_warning_and_disambiguates(
        self,
        mock_environ: dict[str, Any],
        mock_share: MagicMock,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Documents with same sanitized title should be disambiguated."""
        # Two documents with the same title
        doc1 = PaperlessDocument(
            id=1,
            title="Invoice",
            original_file_name="invoice1.pdf",
            created="2025-01-01T00:00:00Z",
            modified="2025-01-01T00:00:00Z",
            tags=[],
        )
        doc2 = PaperlessDocument(
            id=2,
            title="Invoice",
            original_file_name="invoice2.pdf",
            created="2025-01-02T00:00:00Z",
            modified="2025-01-02T00:00:00Z",
            tags=[],
        )
        shares: dict[str, Any] = {"tax2025": mock_share}
        documents_by_share: dict[str, list[PaperlessDocument]] = {
            "tax2025": [doc1, doc2]
        }
        provider = PaperlessProvider(
            shares=shares, documents_by_share=documents_by_share
        )

        share_resource = ShareResource(
            "/tax2025", mock_environ, provider, mock_share
        )
        member_names = share_resource.get_member_names()

        # First document gets original name, second gets disambiguated name
        assert "Invoice.pdf" in member_names
        assert "Invoice_2.pdf" in member_names  # doc2.id = 2
        # Should have logged a warning (structlog logs to stdout)
        captured = capsys.readouterr()
        assert "filename_collision" in captured.out

    def test_collision_in_static_mode_also_disambiguates(
        self,
        mock_environ: dict[str, Any],
        mock_share: MagicMock,
    ) -> None:
        """Static mode (documents_by_share) should also handle collisions."""
        # Two documents with the same title
        doc1 = PaperlessDocument(
            id=10,
            title="Report",
            original_file_name="report1.pdf",
            created="2025-01-01T00:00:00Z",
            modified="2025-01-01T00:00:00Z",
            tags=[],
        )
        doc2 = PaperlessDocument(
            id=20,
            title="Report",
            original_file_name="report2.pdf",
            created="2025-01-02T00:00:00Z",
            modified="2025-01-02T00:00:00Z",
            tags=[],
        )
        shares: dict[str, Any] = {"tax2025": mock_share}
        documents_by_share: dict[str, list[PaperlessDocument]] = {
            "tax2025": [doc1, doc2]
        }

        provider = PaperlessProvider(
            shares=shares, documents_by_share=documents_by_share
        )

        # Provider's static index should have both documents accessible
        assert "Report.pdf" in provider._doc_by_filename["tax2025"]
        assert "Report_20.pdf" in provider._doc_by_filename["tax2025"]

    def test_disambiguated_filename_resolves_to_correct_document(
        self,
        mock_environ: dict[str, Any],
        mock_share: MagicMock,
    ) -> None:
        """Disambiguated filenames should resolve to the correct document."""
        doc1 = PaperlessDocument(
            id=100,
            title="Contract",
            original_file_name="contract1.pdf",
            created="2025-01-01T00:00:00Z",
            modified="2025-01-01T00:00:00Z",
            tags=[],
        )
        doc2 = PaperlessDocument(
            id=200,
            title="Contract",
            original_file_name="contract2.pdf",
            created="2025-01-02T00:00:00Z",
            modified="2025-01-02T00:00:00Z",
            tags=[],
        )
        shares: dict[str, Any] = {"tax2025": mock_share}
        documents_by_share: dict[str, list[PaperlessDocument]] = {
            "tax2025": [doc1, doc2]
        }
        provider = PaperlessProvider(
            shares=shares, documents_by_share=documents_by_share
        )

        # Resolve the disambiguated filename
        resource = provider.get_resource_inst("/tax2025/Contract_200.pdf", mock_environ)

        assert isinstance(resource, DocumentResource)
        assert resource.document.id == 200


# -----------------------------------------------------------------------------
# Download Error Handling Tests
# -----------------------------------------------------------------------------


# -----------------------------------------------------------------------------
# Done Tag Filtering Tests
# -----------------------------------------------------------------------------


class TestDoneTagFiltering:
    """Tests for filtering documents with done_tag from root listing."""

    def test_share_resource_excludes_done_documents_from_root(
        self,
        mock_environ_with_token: dict[str, Any],
        mock_paperless_client: AsyncMock,
    ) -> None:
        """Root listing should exclude documents with done_tag."""
        mock_share = MagicMock()
        mock_share.name = "inbox"
        mock_share.include_tags = ["inbox"]
        mock_share.exclude_tags = []
        mock_share.done_folder_enabled = True
        mock_share.done_folder_name = "processed"
        mock_share.done_tag = "processed"

        # Set up tags including the done_tag
        mock_paperless_client.get_tags.return_value = [
            PaperlessTag(id=1, name="inbox", slug="inbox"),
            PaperlessTag(id=2, name="processed", slug="processed"),
        ]

        # Return two documents - API should be called with exclude_tag_ids=[2]
        # Since we're testing the exclude logic, the mock should return only
        # documents that DON'T have the done_tag (API would filter them)
        mock_paperless_client.get_documents.return_value = [
            PaperlessDocument(
                id=1,
                title="New Doc",
                original_file_name="new.pdf",
                created="2025-01-15T10:00:00Z",
                modified="2025-01-15T10:00:00Z",
                tags=[1],
            ),
            # Note: Done Doc with tag [1, 2] would be filtered by API
        ]

        shares: dict[str, Any] = {"inbox": mock_share}
        provider = PaperlessProvider(
            shares=shares,
            paperless_url="http://paperless.local",
        )

        with patch.object(
            provider, "_create_client", return_value=mock_paperless_client
        ):
            share_resource = ShareResource(
                "/inbox", mock_environ_with_token, provider, mock_share
            )
            members = share_resource.get_member_names()

        # Root should have "New Doc.pdf" and the "processed" folder
        assert "New Doc.pdf" in members
        assert "processed" in members  # Done folder still visible

        # Verify that get_documents was called with done_tag ID in exclude_tag_ids
        mock_paperless_client.get_documents.assert_called_once()
        call_kwargs = mock_paperless_client.get_documents.call_args.kwargs
        assert 2 in call_kwargs.get("exclude_tag_ids", [])  # processed tag id=2

    def test_share_resource_adds_done_tag_to_exclude_tags(
        self,
        mock_environ_with_token: dict[str, Any],
        mock_paperless_client: AsyncMock,
    ) -> None:
        """Done tag should be added to exclude_tag_ids alongside explicit excludes."""
        mock_share = MagicMock()
        mock_share.name = "inbox"
        mock_share.include_tags = ["inbox"]
        mock_share.exclude_tags = ["draft"]  # Explicit exclude
        mock_share.done_folder_enabled = True
        mock_share.done_folder_name = "done"
        mock_share.done_tag = "completed"

        mock_paperless_client.get_tags.return_value = [
            PaperlessTag(id=1, name="inbox", slug="inbox"),
            PaperlessTag(id=2, name="draft", slug="draft"),
            PaperlessTag(id=3, name="completed", slug="completed"),
        ]
        mock_paperless_client.get_documents.return_value = []

        shares: dict[str, Any] = {"inbox": mock_share}
        provider = PaperlessProvider(
            shares=shares,
            paperless_url="http://paperless.local",
        )

        with patch.object(
            provider, "_create_client", return_value=mock_paperless_client
        ):
            share_resource = ShareResource(
                "/inbox", mock_environ_with_token, provider, mock_share
            )
            share_resource.get_member_names()

        # Should exclude both draft (explicit) and completed (done_tag)
        call_kwargs = mock_paperless_client.get_documents.call_args.kwargs
        exclude_ids = call_kwargs.get("exclude_tag_ids", [])
        assert 2 in exclude_ids  # draft
        assert 3 in exclude_ids  # completed (done_tag)

    def test_share_resource_no_done_tag_filtering_when_disabled(
        self,
        mock_environ_with_token: dict[str, Any],
        mock_paperless_client: AsyncMock,
    ) -> None:
        """No done_tag filtering when done_folder_enabled is False."""
        mock_share = MagicMock()
        mock_share.name = "inbox"
        mock_share.include_tags = ["inbox"]
        mock_share.exclude_tags = []
        mock_share.done_folder_enabled = False  # Disabled
        mock_share.done_folder_name = "done"
        mock_share.done_tag = "completed"

        mock_paperless_client.get_tags.return_value = [
            PaperlessTag(id=1, name="inbox", slug="inbox"),
            PaperlessTag(id=3, name="completed", slug="completed"),
        ]
        mock_paperless_client.get_documents.return_value = []

        shares: dict[str, Any] = {"inbox": mock_share}
        provider = PaperlessProvider(
            shares=shares,
            paperless_url="http://paperless.local",
        )

        with patch.object(
            provider, "_create_client", return_value=mock_paperless_client
        ):
            share_resource = ShareResource(
                "/inbox", mock_environ_with_token, provider, mock_share
            )
            share_resource.get_member_names()

        # Should NOT exclude completed tag when done_folder is disabled
        call_kwargs = mock_paperless_client.get_documents.call_args.kwargs
        exclude_ids = call_kwargs.get("exclude_tag_ids", [])
        assert 3 not in exclude_ids  # completed should NOT be excluded

    def test_share_resource_no_done_tag_filtering_when_tag_not_set(
        self,
        mock_environ_with_token: dict[str, Any],
        mock_paperless_client: AsyncMock,
    ) -> None:
        """No done_tag filtering when done_tag is None."""
        mock_share = MagicMock()
        mock_share.name = "inbox"
        mock_share.include_tags = ["inbox"]
        mock_share.exclude_tags = []
        mock_share.done_folder_enabled = True
        mock_share.done_folder_name = "done"
        mock_share.done_tag = None  # Not set

        mock_paperless_client.get_tags.return_value = [
            PaperlessTag(id=1, name="inbox", slug="inbox"),
        ]
        mock_paperless_client.get_documents.return_value = []

        shares: dict[str, Any] = {"inbox": mock_share}
        provider = PaperlessProvider(
            shares=shares,
            paperless_url="http://paperless.local",
        )

        with patch.object(
            provider, "_create_client", return_value=mock_paperless_client
        ):
            share_resource = ShareResource(
                "/inbox", mock_environ_with_token, provider, mock_share
            )
            share_resource.get_member_names()

        # Should have empty exclude_tag_ids since done_tag is None
        call_kwargs = mock_paperless_client.get_documents.call_args.kwargs
        exclude_ids = call_kwargs.get("exclude_tag_ids", [])
        assert exclude_ids == []

    def test_share_resource_handles_missing_done_tag_gracefully(
        self,
        mock_environ_with_token: dict[str, Any],
        mock_paperless_client: AsyncMock,
    ) -> None:
        """Should handle gracefully when done_tag doesn't exist in Paperless."""
        mock_share = MagicMock()
        mock_share.name = "inbox"
        mock_share.include_tags = ["inbox"]
        mock_share.exclude_tags = []
        mock_share.done_folder_enabled = True
        mock_share.done_folder_name = "done"
        mock_share.done_tag = "nonexistent-tag"  # Tag doesn't exist

        mock_paperless_client.get_tags.return_value = [
            PaperlessTag(id=1, name="inbox", slug="inbox"),
            # Note: "nonexistent-tag" is not in the list
        ]
        mock_paperless_client.get_documents.return_value = []

        shares: dict[str, Any] = {"inbox": mock_share}
        provider = PaperlessProvider(
            shares=shares,
            paperless_url="http://paperless.local",
        )

        with patch.object(
            provider, "_create_client", return_value=mock_paperless_client
        ):
            share_resource = ShareResource(
                "/inbox", mock_environ_with_token, provider, mock_share
            )
            # Should not raise, even though done_tag doesn't exist
            share_resource.get_member_names()

        # Should have called get_documents (even if done_tag wasn't found)
        mock_paperless_client.get_documents.assert_called_once()


# -----------------------------------------------------------------------------
# Download Error Handling Tests
# -----------------------------------------------------------------------------


class TestDownloadErrorHandling:
    """Tests for error handling during document download."""

    def test_download_error_returns_empty_bytes_and_logs(
        self,
        mock_environ_with_token: dict[str, Any],
        mock_share: MagicMock,
        sample_document: PaperlessDocument,
        mock_paperless_client: AsyncMock,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Download errors should be caught, logged, and return empty bytes."""
        mock_paperless_client.download_document.side_effect = Exception(
            "Connection timeout"
        )

        shares: dict[str, Any] = {"tax2025": mock_share}
        provider = PaperlessProvider(
            shares=shares,
            paperless_url="http://paperless.local",
        )

        with patch.object(
            provider, "_create_client", return_value=mock_paperless_client
        ):
            doc_resource = DocumentResource(
                "/tax2025/Tax Invoice 2025.pdf",
                mock_environ_with_token,
                provider,
                sample_document,
            )
            content_stream = doc_resource.get_content()

        # Should return empty bytes
        assert content_stream.read() == b""
        # Should have logged an error (structlog logs to stdout)
        captured = capsys.readouterr()
        assert "download_document_failed" in captured.out

    def test_download_error_caches_empty_bytes(
        self,
        mock_environ_with_token: dict[str, Any],
        mock_share: MagicMock,
        sample_document: PaperlessDocument,
        mock_paperless_client: AsyncMock,
    ) -> None:
        """After download error, subsequent calls should return cached empty bytes."""
        mock_paperless_client.download_document.side_effect = Exception("API error")

        shares: dict[str, Any] = {"tax2025": mock_share}
        provider = PaperlessProvider(
            shares=shares,
            paperless_url="http://paperless.local",
        )

        with patch.object(
            provider, "_create_client", return_value=mock_paperless_client
        ):
            doc_resource = DocumentResource(
                "/tax2025/Tax Invoice 2025.pdf",
                mock_environ_with_token,
                provider,
                sample_document,
            )
            # First call triggers download error
            doc_resource.get_content()
            # Second call should use cached empty bytes
            content_stream = doc_resource.get_content()

        # Should return empty bytes
        assert content_stream.read() == b""
        # Download should only have been attempted once
        assert mock_paperless_client.download_document.call_count == 1

    def test_content_length_is_zero_after_download_error(
        self,
        mock_environ_with_token: dict[str, Any],
        mock_share: MagicMock,
        sample_document: PaperlessDocument,
        mock_paperless_client: AsyncMock,
    ) -> None:
        """Content length should be 0 after a download error."""
        mock_paperless_client.download_document.side_effect = Exception("Network error")

        shares: dict[str, Any] = {"tax2025": mock_share}
        provider = PaperlessProvider(
            shares=shares,
            paperless_url="http://paperless.local",
        )

        with patch.object(
            provider, "_create_client", return_value=mock_paperless_client
        ):
            doc_resource = DocumentResource(
                "/tax2025/Tax Invoice 2025.pdf",
                mock_environ_with_token,
                provider,
                sample_document,
            )
            # Trigger download error
            doc_resource.get_content()
            # Check content length
            length = doc_resource.get_content_length()

        # Should be 0 (length of empty bytes)
        assert length == 0
