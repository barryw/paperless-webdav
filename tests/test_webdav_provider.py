# tests/test_webdav_provider.py
"""Tests for the WebDAV provider."""

from datetime import datetime
from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from paperless_webdav.paperless_client import PaperlessDocument
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
