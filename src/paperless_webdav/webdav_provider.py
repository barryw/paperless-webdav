# src/paperless_webdav/webdav_provider.py
"""WsgiDAV provider for Paperless-ngx documents.

This module implements a WebDAV provider that exposes Paperless documents
through a virtual filesystem. The hierarchy is:

    /                           - Root (lists all shares)
    /{sharename}/               - Share (lists documents filtered by tags)
    /{sharename}/{title}.pdf    - Document (serves PDF content)
    /{sharename}/done/          - Done folder (for marking documents processed)

The provider bridges file manager clients (e.g., macOS Finder, Windows Explorer)
with the Paperless-ngx document management system.
"""

from __future__ import annotations

import io
import re
from datetime import datetime
from typing import TYPE_CHECKING, Any

from wsgidav.dav_provider import DAVCollection, DAVNonCollection, DAVProvider  # type: ignore[import-untyped]

from paperless_webdav.async_bridge import run_async
from paperless_webdav.logging import get_logger
from paperless_webdav.paperless_client import PaperlessClient, PaperlessDocument

if TYPE_CHECKING:
    from paperless_webdav.models import Share

logger = get_logger(__name__)


# Characters that are unsafe for filesystems (Windows, macOS, Linux)
UNSAFE_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*]')


def sanitize_filename(name: str) -> str:
    """Remove filesystem-unsafe characters from a filename.

    Removes characters that could cause issues on various filesystems:
    - Path separators: / \\
    - Windows reserved: < > : " | ? *

    Args:
        name: The original filename or document title

    Returns:
        A sanitized filename safe for use on any filesystem.
        Returns "untitled" if the result would be empty.
    """
    # Remove unsafe characters
    sanitized = UNSAFE_FILENAME_CHARS.sub("", name)

    # Strip whitespace
    sanitized = sanitized.strip()

    # Return default if empty
    if not sanitized:
        return "untitled"

    return sanitized


class PaperlessProvider(DAVProvider):  # type: ignore[misc]
    """WebDAV provider that serves Paperless-ngx documents.

    This provider maps WebDAV paths to Paperless resources:
    - / returns a RootResource listing all shares
    - /{share} returns a ShareResource listing documents
    - /{share}/{doc}.pdf returns a DocumentResource for the PDF

    The provider maintains a reference to available shares and their
    documents. In production, documents are fetched dynamically from
    the Paperless API using the user's token from the WSGI environ.
    """

    def __init__(
        self,
        shares: dict[str, Share] | None = None,
        documents_by_share: dict[str, list[PaperlessDocument]] | None = None,
        paperless_url: str | None = None,
    ) -> None:
        """Initialize the provider.

        Args:
            shares: Dictionary mapping share names to Share objects
            documents_by_share: Dictionary mapping share names to document lists
                (for backward compatibility / static mode)
            paperless_url: Base URL of the Paperless-ngx instance for dynamic
                document loading
        """
        super().__init__()
        self._shares: dict[str, Share] = shares or {}
        self._documents_by_share: dict[str, list[PaperlessDocument]] = (
            documents_by_share or {}
        )
        self._paperless_url: str | None = paperless_url
        # Build filename-to-document mapping for each share (static mode)
        self._doc_by_filename: dict[str, dict[str, PaperlessDocument]] = {}
        self._build_filename_index()

    def _build_filename_index(self) -> None:
        """Build index mapping sanitized filenames to documents.

        When multiple documents would have the same sanitized filename,
        a warning is logged and the document ID is appended to disambiguate.
        """
        self._doc_by_filename = {}
        for share_name, documents in self._documents_by_share.items():
            self._doc_by_filename[share_name] = {}
            for doc in documents:
                base_name = sanitize_filename(doc.title)
                filename = f"{base_name}.pdf"
                if filename in self._doc_by_filename[share_name]:
                    # Collision detected - append document ID to disambiguate
                    existing_doc = self._doc_by_filename[share_name][filename]
                    logger.warning(
                        "filename_collision",
                        share=share_name,
                        filename=filename,
                        doc_id=doc.id,
                        existing_doc_id=existing_doc.id,
                    )
                    filename = f"{base_name}_{doc.id}.pdf"
                self._doc_by_filename[share_name][filename] = doc

    def _create_client(self, environ: dict[str, Any]) -> PaperlessClient | None:
        """Create a PaperlessClient from WSGI environ.

        The token is expected to be stored in environ["paperless.token"] by
        the authentication middleware.

        Args:
            environ: WSGI environ dictionary

        Returns:
            PaperlessClient if token is available, None otherwise
        """
        token = environ.get("paperless.token")
        if not token or not self._paperless_url:
            return None
        return PaperlessClient(self._paperless_url, token)

    def get_resource_inst(
        self, path: str, environ: dict[str, Any]
    ) -> RootResource | ShareResource | DocumentResource | DoneFolderResource | None:
        """Resolve a WebDAV path to the appropriate resource.

        Args:
            path: The WebDAV request path (e.g., "/share/document.pdf")
            environ: WSGI environ dictionary

        Returns:
            The appropriate DAV resource, or None if not found
        """
        # Normalize path
        path = path.rstrip("/")
        if not path:
            path = "/"

        parts = [p for p in path.split("/") if p]

        # Root: /
        if len(parts) == 0:
            logger.debug("resolve_root", path=path)
            return RootResource(path, environ, self)

        share_name = parts[0]

        # Check if share exists
        if share_name not in self._shares:
            logger.debug("share_not_found", share_name=share_name)
            return None

        share = self._shares[share_name]

        # Share: /{sharename}
        if len(parts) == 1:
            logger.debug("resolve_share", share_name=share_name)
            return ShareResource(path, environ, self, share)

        resource_name = parts[1]

        # Done folder: /{sharename}/done
        if resource_name == share.done_folder_name and share.done_folder_enabled:
            logger.debug("resolve_done_folder", share_name=share_name)
            return DoneFolderResource(path, environ, self, share)

        # Document: /{sharename}/{filename}.pdf
        if share_name in self._doc_by_filename:
            doc = self._doc_by_filename[share_name].get(resource_name)
            if doc is not None:
                logger.debug(
                    "resolve_document",
                    share_name=share_name,
                    document_id=doc.id,
                )
                return DocumentResource(path, environ, self, doc, share=share)

        logger.debug("resource_not_found", path=path)
        return None

    def get_documents_for_share(self, share_name: str) -> list[PaperlessDocument]:
        """Get documents for a specific share.

        Args:
            share_name: Name of the share

        Returns:
            List of documents in the share
        """
        return self._documents_by_share.get(share_name, [])


class RootResource(DAVCollection):  # type: ignore[misc]
    """WebDAV collection representing the root directory.

    Lists all available shares as subdirectories.
    """

    def __init__(
        self, path: str, environ: dict[str, Any], provider: PaperlessProvider
    ) -> None:
        """Initialize the root resource.

        Args:
            path: The WebDAV path (should be "/")
            environ: WSGI environ dictionary
            provider: The parent PaperlessProvider
        """
        super().__init__(path, environ)
        self._provider = provider

    def get_member_names(self) -> list[str]:
        """Return list of available share names.

        Returns:
            List of share names that appear as directories
        """
        return list(self._provider._shares.keys())

    def get_member(self, name: str) -> ShareResource | None:
        """Get a share by name.

        Args:
            name: The share name

        Returns:
            ShareResource if found, None otherwise
        """
        if name in self._provider._shares:
            share = self._provider._shares[name]
            return ShareResource(f"/{name}", self.environ, self._provider, share)
        return None


class ShareResource(DAVCollection):  # type: ignore[misc]
    """WebDAV collection representing a share directory.

    Lists documents filtered by the share's tag configuration.
    """

    def __init__(
        self,
        path: str,
        environ: dict[str, Any],
        provider: PaperlessProvider,
        share: Share,
    ) -> None:
        """Initialize the share resource.

        Args:
            path: The WebDAV path (e.g., "/sharename")
            environ: WSGI environ dictionary
            provider: The parent PaperlessProvider
            share: The Share configuration object
        """
        super().__init__(path, environ)
        self._provider = provider
        self._share = share
        # Cache for dynamically loaded documents
        self._loaded_documents: list[PaperlessDocument] | None = None
        self._doc_by_filename: dict[str, PaperlessDocument] | None = None

    def get_display_name(self) -> str:
        """Return the share name for display.

        Returns:
            The share's configured name
        """
        return self._share.name

    def _resolve_tag_ids_from_map(
        self, tag_map: dict[str, int], tag_names: list[str]
    ) -> list[int]:
        """Resolve tag names to tag IDs using a pre-fetched tag map.

        Args:
            tag_map: Dictionary mapping tag names to tag IDs
            tag_names: List of tag names to resolve

        Returns:
            List of tag IDs for tags that exist
        """
        if not tag_names:
            return []

        resolved_ids = []
        for name in tag_names:
            if name in tag_map:
                resolved_ids.append(tag_map[name])
            else:
                logger.warning("tag_not_found", tag_name=name, share=self._share.name)

        return resolved_ids

    def _load_documents(self) -> list[PaperlessDocument]:
        """Load documents from Paperless API or static cache.

        Attempts dynamic loading if a client can be created. Falls back
        to static documents_by_share if no client is available.

        Returns:
            List of documents for this share
        """
        # Check if we can use dynamic loading
        client = self._provider._create_client(self.environ)
        if client is not None:
            # Fetch all tags once and build name->id map
            all_tags = run_async(client.get_tags())
            tag_map = {tag.name: tag.id for tag in all_tags}

            # Resolve tag names to IDs using the shared map
            include_tag_ids = self._resolve_tag_ids_from_map(
                tag_map, list(self._share.include_tags)
            )
            exclude_tag_ids = self._resolve_tag_ids_from_map(
                tag_map, list(self._share.exclude_tags)
            )

            # When done folder is enabled, exclude documents with done_tag from root
            # (they should only appear in the done folder, not in the share root)
            if self._share.done_folder_enabled and self._share.done_tag:
                done_tag_ids = self._resolve_tag_ids_from_map(
                    tag_map, [self._share.done_tag]
                )
                exclude_tag_ids.extend(done_tag_ids)

            # Fetch documents with tag filters
            documents = run_async(
                client.get_documents(
                    include_tag_ids=include_tag_ids,
                    exclude_tag_ids=exclude_tag_ids,
                )
            )
            logger.debug(
                "loaded_documents_dynamically",
                share=self._share.name,
                count=len(documents),
            )
            return documents

        # Fall back to static mode
        return self._provider.get_documents_for_share(self._share.name)

    def _get_documents(self) -> list[PaperlessDocument]:
        """Get documents for this share, caching for the request.

        When multiple documents have the same sanitized filename,
        a warning is logged and the document ID is appended to disambiguate.

        Returns:
            List of documents for this share
        """
        if self._loaded_documents is None:
            self._loaded_documents = self._load_documents()
            # Build filename index with collision detection
            self._doc_by_filename = {}
            for doc in self._loaded_documents:
                base_name = sanitize_filename(doc.title)
                filename = f"{base_name}.pdf"
                if filename in self._doc_by_filename:
                    # Collision detected - append document ID to disambiguate
                    existing_doc = self._doc_by_filename[filename]
                    logger.warning(
                        "filename_collision",
                        share=self._share.name,
                        filename=filename,
                        doc_id=doc.id,
                        existing_doc_id=existing_doc.id,
                    )
                    filename = f"{base_name}_{doc.id}.pdf"
                self._doc_by_filename[filename] = doc
        return self._loaded_documents

    def _get_doc_by_filename(self, filename: str) -> PaperlessDocument | None:
        """Get a document by its sanitized filename.

        Args:
            filename: The sanitized filename (e.g., "Invoice.pdf")

        Returns:
            PaperlessDocument if found, None otherwise
        """
        # Ensure documents are loaded
        self._get_documents()
        if self._doc_by_filename is not None:
            return self._doc_by_filename.get(filename)
        return None

    def get_member_names(self) -> list[str]:
        """Return list of document filenames in this share.

        Documents are listed as "{sanitized_title}.pdf" or "{sanitized_title}_{id}.pdf"
        if collision disambiguation was needed.
        If done folder is enabled, it's included in the listing.

        Returns:
            List of member names (documents and optionally done folder)
        """
        members: list[str] = []

        # Add done folder if enabled
        if self._share.done_folder_enabled:
            members.append(self._share.done_folder_name)

        # Ensure documents are loaded (this builds the filename index)
        self._get_documents()

        # Add document filenames from the index (includes collision suffixes)
        if self._doc_by_filename is not None:
            members.extend(self._doc_by_filename.keys())

        return members

    def get_member(
        self, name: str
    ) -> DocumentResource | DoneFolderResource | None:
        """Get a member resource by name.

        Args:
            name: The filename or folder name

        Returns:
            The appropriate resource, or None if not found
        """
        # Check for done folder
        if name == self._share.done_folder_name and self._share.done_folder_enabled:
            return DoneFolderResource(
                f"{self.path}/{name}", self.environ, self._provider, self._share
            )

        # Check for document - try dynamic first, then static
        doc = self._get_doc_by_filename(name)
        if doc is not None:
            return DocumentResource(
                f"{self.path}/{name}",
                self.environ,
                self._provider,
                doc,
                share=self._share,
            )

        # Fall back to static index if dynamic didn't find it
        share_name = self._share.name
        if share_name in self._provider._doc_by_filename:
            doc = self._provider._doc_by_filename[share_name].get(name)
            if doc is not None:
                return DocumentResource(
                    f"{self.path}/{name}",
                    self.environ,
                    self._provider,
                    doc,
                    share=self._share,
                )

        return None


class DoneFolderResource(DAVCollection):  # type: ignore[misc]
    """WebDAV collection representing the "done" folder.

    Lists documents that have been tagged with the share's done_tag,
    indicating they have been processed.
    """

    def __init__(
        self,
        path: str,
        environ: dict[str, Any],
        provider: PaperlessProvider,
        share: Share,
    ) -> None:
        """Initialize the done folder resource.

        Args:
            path: The WebDAV path (e.g., "/sharename/done")
            environ: WSGI environ dictionary
            provider: The parent PaperlessProvider
            share: The Share configuration object
        """
        super().__init__(path, environ)
        self._provider = provider
        self._share = share
        # Cache for dynamically loaded documents
        self._loaded_documents: list[PaperlessDocument] | None = None
        self._doc_by_filename: dict[str, PaperlessDocument] | None = None

    def get_display_name(self) -> str:
        """Return the done folder name for display.

        Returns:
            The share's configured done folder name
        """
        return self._share.done_folder_name

    def _resolve_tag_ids_from_map(
        self, tag_map: dict[str, int], tag_names: list[str]
    ) -> list[int]:
        """Resolve tag names to tag IDs using a pre-fetched tag map.

        Args:
            tag_map: Dictionary mapping tag names to tag IDs
            tag_names: List of tag names to resolve

        Returns:
            List of tag IDs for tags that exist
        """
        if not tag_names:
            return []

        resolved_ids = []
        for name in tag_names:
            if name in tag_map:
                resolved_ids.append(tag_map[name])
            else:
                logger.warning("tag_not_found", tag_name=name, share=self._share.name)

        return resolved_ids

    def _load_documents(self) -> list[PaperlessDocument]:
        """Load documents with done_tag from Paperless API.

        Returns:
            List of documents that have the done_tag
        """
        client = self._provider._create_client(self.environ)
        if client is not None:
            # Fetch all tags once and build name->id map
            all_tags = run_async(client.get_tags())
            tag_map = {tag.name: tag.id for tag in all_tags}

            # Include tags: share's include_tags AND the done_tag
            # This ensures we only show documents that belong to this share
            # and are marked as done
            include_tag_ids = self._resolve_tag_ids_from_map(
                tag_map, list(self._share.include_tags)
            )

            # Add done_tag to include list (documents must have this tag)
            if self._share.done_tag:
                done_tag_ids = self._resolve_tag_ids_from_map(
                    tag_map, [self._share.done_tag]
                )
                include_tag_ids.extend(done_tag_ids)

            # Exclude tags: share's exclude_tags (but NOT the done_tag)
            exclude_tag_ids = self._resolve_tag_ids_from_map(
                tag_map, list(self._share.exclude_tags)
            )

            # Fetch documents with tag filters
            documents = run_async(
                client.get_documents(
                    include_tag_ids=include_tag_ids,
                    exclude_tag_ids=exclude_tag_ids,
                )
            )
            logger.debug(
                "loaded_done_documents",
                share=self._share.name,
                count=len(documents),
            )
            return documents

        # No client available - return empty list
        return []

    def _get_documents(self) -> list[PaperlessDocument]:
        """Get documents for this done folder, caching for the request.

        When multiple documents have the same sanitized filename,
        a warning is logged and the document ID is appended to disambiguate.

        Returns:
            List of documents with done_tag
        """
        if self._loaded_documents is None:
            self._loaded_documents = self._load_documents()
            # Build filename index with collision detection
            self._doc_by_filename = {}
            for doc in self._loaded_documents:
                base_name = sanitize_filename(doc.title)
                filename = f"{base_name}.pdf"
                if filename in self._doc_by_filename:
                    # Collision detected - append document ID to disambiguate
                    existing_doc = self._doc_by_filename[filename]
                    logger.warning(
                        "filename_collision",
                        share=self._share.name,
                        folder="done",
                        filename=filename,
                        doc_id=doc.id,
                        existing_doc_id=existing_doc.id,
                    )
                    filename = f"{base_name}_{doc.id}.pdf"
                self._doc_by_filename[filename] = doc
        return self._loaded_documents

    def _get_doc_by_filename(self, filename: str) -> PaperlessDocument | None:
        """Get a document by its sanitized filename.

        Args:
            filename: The sanitized filename (e.g., "Invoice.pdf")

        Returns:
            PaperlessDocument if found, None otherwise
        """
        # Ensure documents are loaded
        self._get_documents()
        if self._doc_by_filename is not None:
            return self._doc_by_filename.get(filename)
        return None

    def get_member_names(self) -> list[str]:
        """Return list of documents in the done folder.

        Documents are listed as "{sanitized_title}.pdf" or "{sanitized_title}_{id}.pdf"
        if collision disambiguation was needed.

        Returns:
            List of document filenames with done_tag
        """
        # Ensure documents are loaded (this builds the filename index)
        self._get_documents()

        # Return document filenames from the index (includes collision suffixes)
        if self._doc_by_filename is not None:
            return list(self._doc_by_filename.keys())

        return []

    def get_member(self, name: str) -> DocumentResource | None:
        """Get a member by name.

        Args:
            name: The filename

        Returns:
            DocumentResource if found, None otherwise
        """
        doc = self._get_doc_by_filename(name)
        if doc is not None:
            return DocumentResource(
                f"{self.path}/{name}",
                self.environ,
                self._provider,
                doc,
                share=self._share,
            )
        return None


class DocumentResource(DAVNonCollection):  # type: ignore[misc]
    """WebDAV resource representing a Paperless document.

    Exposes document metadata (dates, etag) and content as a PDF file.
    Supports move operations to done folder (adds done_tag).
    """

    def __init__(
        self,
        path: str,
        environ: dict[str, Any],
        provider: PaperlessProvider,
        document: PaperlessDocument,
        share: Share | None = None,
    ) -> None:
        """Initialize the document resource.

        Args:
            path: The WebDAV path (e.g., "/share/document.pdf")
            environ: WSGI environ dictionary
            provider: The parent PaperlessProvider
            document: The PaperlessDocument metadata
            share: Optional Share configuration (needed for move operations)
        """
        super().__init__(path, environ)
        self._provider = provider
        self.document = document
        self._share: Share | None = share
        # Cache for downloaded content
        self._content: bytes | None = None

    def get_display_name(self) -> str:
        """Return the document filename for display.

        Returns:
            Sanitized document title with .pdf extension
        """
        return f"{sanitize_filename(self.document.title)}.pdf"

    def get_content_type(self) -> str:
        """Return the MIME type for the document.

        Returns:
            'application/pdf' for all documents
        """
        return "application/pdf"

    def _download_content(self) -> bytes:
        """Download document content from Paperless API.

        Returns:
            Document content as bytes, or empty bytes on error
        """
        if self._content is not None:
            return self._content

        client = self._provider._create_client(self.environ)
        if client is not None:
            try:
                self._content = run_async(client.download_document(self.document.id))
                logger.debug(
                    "downloaded_document_content",
                    document_id=self.document.id,
                    size=len(self._content),
                )
                return self._content
            except Exception as exc:
                logger.error(
                    "download_document_failed",
                    document_id=self.document.id,
                    error=str(exc),
                )
                self._content = b""
                return self._content

        # No client available - return empty bytes
        logger.warning(
            "no_client_for_download",
            document_id=self.document.id,
        )
        return b""

    def get_content_length(self) -> int:
        """Return the content length.

        Returns the actual size of the document content. If content has
        been downloaded, returns its length. Otherwise returns -1 to
        indicate unknown length.

        Note: Returning -1 before download is intentional behavior.
        WsgiDAV handles this gracefully by using HTTP chunked transfer
        encoding, avoiding an extra API call just to get the content size.

        Returns:
            Content length in bytes, or -1 if unknown (triggers chunked transfer)
        """
        if self._content is not None:
            return len(self._content)
        # Intentionally return -1 before download - wsgidav will use
        # chunked transfer encoding, which is acceptable behavior
        return -1

    def get_content(self) -> io.BytesIO:
        """Return the document content as a file-like object.

        Downloads the document content from Paperless API and returns
        it as a BytesIO stream.

        Returns:
            File-like object containing document content
        """
        content = self._download_content()
        return io.BytesIO(content)

    def get_creation_date(self) -> datetime:
        """Return the document creation date.

        Returns:
            The document's created timestamp
        """
        return self._parse_iso_datetime(self.document.created)

    def get_last_modified(self) -> datetime:
        """Return the document modification date.

        Returns:
            The document's modified timestamp
        """
        return self._parse_iso_datetime(self.document.modified)

    def get_etag(self) -> str:
        """Return an etag for cache validation.

        The etag is based on document ID and modification time,
        allowing clients to detect when documents have changed.

        Returns:
            A string etag value
        """
        return f'"{self.document.id}-{self.document.modified}"'

    def support_etag(self) -> bool:
        """Indicate whether this resource supports etags.

        Returns:
            True, as documents always have etags
        """
        return True

    @staticmethod
    def _parse_iso_datetime(iso_string: str) -> datetime:
        """Parse an ISO 8601 datetime string.

        Args:
            iso_string: ISO formatted datetime (e.g., "2025-01-15T10:30:00Z")

        Returns:
            A datetime object
        """
        # Handle both Z suffix and +00:00 formats
        if iso_string.endswith("Z"):
            iso_string = iso_string[:-1] + "+00:00"
        return datetime.fromisoformat(iso_string)

    def _is_move_to_done_folder(self, dest_path: str) -> bool:
        """Check if the destination path is the done folder.

        Args:
            dest_path: The destination path (e.g., "/inbox/done/Doc.pdf")

        Returns:
            True if the destination is inside the done folder
        """
        if self._share is None:
            return False
        if not self._share.done_folder_enabled:
            return False

        # Parse destination path: /{share_name}/{done_folder_name}/{filename}
        parts = [p for p in dest_path.split("/") if p]
        if len(parts) < 3:
            return False

        share_name = parts[0]
        folder_name = parts[1]

        # Check if it's moving to this share's done folder
        return (
            share_name == self._share.name
            and folder_name == self._share.done_folder_name
        )

    def _get_done_tag_id(self) -> int | None:
        """Get the done_tag ID by resolving the tag name.

        Returns:
            Tag ID if found, None otherwise
        """
        if self._share is None or not self._share.done_tag:
            return None

        client = self._provider._create_client(self.environ)
        if client is None:
            return None

        # Fetch all tags and find the done_tag
        try:
            all_tags = run_async(client.get_tags())
        except Exception as exc:
            logger.error("get_tags_failed_during_move", error=str(exc))
            return None
        tag_map = {tag.name: tag.id for tag in all_tags}

        return tag_map.get(self._share.done_tag)

    def move(self, dest_path: str) -> bool:
        """Move the document to a new location.

        When moving to the done folder, this adds the done_tag to the document.
        The move is virtual - we're just adding a tag, not moving files.

        Args:
            dest_path: The destination path

        Returns:
            True if the move was successful
        """
        if not self._is_move_to_done_folder(dest_path):
            logger.debug(
                "move_not_to_done_folder",
                document_id=self.document.id,
                dest_path=dest_path,
            )
            return True  # No-op for moves not to done folder

        # Get the done_tag ID
        done_tag_id = self._get_done_tag_id()
        if done_tag_id is None:
            logger.warning(
                "done_tag_not_found",
                document_id=self.document.id,
                done_tag=self._share.done_tag if self._share else None,
            )
            return True  # No-op if tag not found

        # Add the done_tag to the document
        client = self._provider._create_client(self.environ)
        if client is None:
            logger.warning(
                "no_client_for_move",
                document_id=self.document.id,
            )
            return False

        try:
            run_async(client.add_tag_to_document(self.document.id, done_tag_id))
            logger.info(
                "moved_to_done_folder",
                document_id=self.document.id,
                done_tag_id=done_tag_id,
            )
            return True
        except Exception as exc:
            logger.error(
                "move_to_done_folder_failed",
                document_id=self.document.id,
                done_tag_id=done_tag_id,
                error=str(exc),
            )
            return False
