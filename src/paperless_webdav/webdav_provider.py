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
from typing import TYPE_CHECKING, Any, Callable

from wsgidav.dav_provider import DAVCollection, DAVNonCollection, DAVProvider  # type: ignore[import-untyped]

from paperless_webdav.async_bridge import run_async
from paperless_webdav.cache import get_cache
from paperless_webdav.logging import get_logger
from paperless_webdav.paperless_client import PaperlessClient, PaperlessDocument

# Type alias for clarity
DocumentList = list[PaperlessDocument]


def prefetch_document_sizes(client: PaperlessClient, documents: DocumentList) -> None:
    """Pre-fetch and cache sizes for all documents concurrently.

    This issues concurrent HEAD requests for all documents to populate
    the size cache, avoiding sequential requests during PROPFIND.

    Args:
        client: The PaperlessClient to use
        documents: List of documents to pre-fetch sizes for
    """
    if not documents:
        return

    cache = get_cache()

    # Filter out documents whose sizes are already cached
    doc_ids_to_fetch = [doc.id for doc in documents if cache.get_size(doc.id) is None]

    if not doc_ids_to_fetch:
        logger.debug("prefetch_all_cached", total=len(documents))
        return

    logger.debug(
        "prefetch_starting",
        total=len(documents),
        to_fetch=len(doc_ids_to_fetch),
    )

    try:
        # Fetch sizes concurrently
        sizes = run_async(client.get_document_sizes_batch(doc_ids_to_fetch))

        # Cache all fetched sizes
        for doc_id, size in sizes.items():
            cache.set_size(doc_id, size)

        logger.debug(
            "prefetch_complete",
            requested=len(doc_ids_to_fetch),
            fetched=len(sizes),
        )
    except Exception as e:
        # Don't fail document listing if prefetch fails
        logger.warning("prefetch_failed", error=str(e))


if TYPE_CHECKING:
    from paperless_webdav.models import Share

logger = get_logger(__name__)


# Characters that are unsafe for filesystems (Windows, macOS, Linux)
UNSAFE_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*]')

# macOS metadata file patterns
MACOS_METADATA_PATTERNS = (
    ".DS_Store",
    "._.DS_Store",
    ".Spotlight-V100",
    ".Trashes",
    ".fseventsd",
)


def is_macos_metadata_file(name: str) -> bool:
    """Check if a filename is a macOS metadata file that should be silently handled.

    Args:
        name: The filename to check

    Returns:
        True if this is a macOS metadata file (._*, .DS_Store, etc.)
    """
    if name.startswith("._"):
        return True
    if name in MACOS_METADATA_PATTERNS:
        return True
    return False


class MacOSMetadataResource(DAVNonCollection):  # type: ignore[misc]
    """Virtual resource for macOS metadata files (._*, .DS_Store).

    This resource accepts writes but discards the data, allowing macOS Finder
    to perform operations like MOVE without failing on metadata file writes.
    """

    def __init__(self, path: str, environ: dict[str, Any]) -> None:
        super().__init__(path, environ)
        self._content: bytes = b""

    def get_content_length(self) -> int:
        return len(self._content)

    def get_content_type(self) -> str:
        return "application/octet-stream"

    def get_content(self) -> io.BytesIO:
        return io.BytesIO(self._content)

    def begin_write(self, content_type: str | None = None) -> io.BytesIO:
        """Accept write but discard content."""
        logger.debug("macos_metadata_write", path=self.path)
        # Return a BytesIO that we'll discard
        return io.BytesIO()

    def end_write(self, with_errors: bool) -> None:
        """Complete the write (data is discarded)."""
        pass

    def delete(self) -> None:
        """Accept delete (no-op)."""
        logger.debug("macos_metadata_delete", path=self.path)

    def support_etag(self) -> bool:
        return False

    def get_etag(self) -> str | None:
        """Return None since we don't support etags for metadata files."""
        return None

    def get_creation_date(self) -> float:
        return datetime.now().timestamp()

    def get_last_modified(self) -> float:
        return datetime.now().timestamp()


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
        share_loader: Callable[[], dict[str, Any]] | None = None,
    ) -> None:
        """Initialize the provider.

        Args:
            shares: Dictionary mapping share names to Share objects
            documents_by_share: Dictionary mapping share names to document lists
                (for backward compatibility / static mode)
            paperless_url: Base URL of the Paperless-ngx instance for dynamic
                document loading
            share_loader: Callable that returns dict of share configs (for dynamic loading)
        """
        super().__init__()
        self._shares: dict[str, Share] = shares or {}
        self._documents_by_share: dict[str, list[PaperlessDocument]] = documents_by_share or {}
        self._paperless_url: str | None = paperless_url
        self._share_loader: Callable[[], dict[str, Any]] | None = share_loader
        # Build filename-to-document mapping for each share (static mode)
        self._doc_by_filename: dict[str, dict[str, PaperlessDocument]] = {}
        self._build_filename_index()

    def _build_filename_index(self) -> None:
        """Build index mapping sanitized filenames to documents.

        When multiple documents would have the same sanitized filename,
        a warning is logged and the document ID is appended to disambiguate.
        The document with the LOWEST ID always gets the base filename to ensure
        deterministic behavior across requests.
        """
        self._doc_by_filename = {}
        for share_name, documents in self._documents_by_share.items():
            self._doc_by_filename[share_name] = {}
            # Sort by ID to ensure deterministic collision resolution
            for doc in sorted(documents, key=lambda d: d.id):
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

    def _get_shares(self) -> dict[str, Share]:
        """Get current shares, loading dynamically if share_loader is set.

        Returns:
            Dictionary mapping share names to Share objects
        """
        if self._share_loader is not None:
            # Reload shares from database on each request
            self._shares = self._share_loader()
            logger.debug("loaded_shares", count=len(self._shares))
        return self._shares

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
        logger.debug("get_resource_inst_called", path=path)

        # Normalize path
        path = path.rstrip("/")
        if not path:
            path = "/"

        parts = [p for p in path.split("/") if p]

        # Load shares dynamically
        shares = self._get_shares()

        # Root: /
        if len(parts) == 0:
            logger.debug("resolve_root", path=path)
            return RootResource(path, environ, self)

        share_name = parts[0]

        # Check if share exists
        if share_name not in shares:
            logger.debug(
                "share_not_found", share_name=share_name, available_shares=list(shares.keys())
            )
            return None

        share = shares[share_name]

        # Share: /{sharename}
        if len(parts) == 1:
            logger.debug("resolve_share", share_name=share_name)
            return ShareResource(path, environ, self, share)

        resource_name = parts[1]

        # Use ShareResource to resolve members (handles dynamic loading)
        share_resource = ShareResource(f"/{share_name}", environ, self, share)
        member = share_resource.get_member(resource_name)

        if member is None:
            logger.debug("resource_not_found", path=path)
            return None

        # Two-level path: /{share}/{resource} (document or done folder)
        if len(parts) == 2:
            member.path = path
            logger.debug(
                "resolve_two_level",
                path=path,
                resource_type=type(member).__name__,
                is_collection=member.is_collection,
            )
            return member

        # Three-level path: /{share}/done/{document}
        # Need to resolve the document within the done folder
        if len(parts) == 3:
            logger.debug(
                "resolve_three_level",
                path=path,
                member_type=type(member).__name__,
                is_done_folder=isinstance(member, DoneFolderResource),
            )
            if isinstance(member, DoneFolderResource):
                doc_name = parts[2]
                doc_resource = member.get_member(doc_name)
                if doc_resource is not None:
                    doc_resource.path = path
                    return doc_resource
                logger.debug("document_not_found_in_done", path=path, doc_name=doc_name)
                return None

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

    def __init__(self, path: str, environ: dict[str, Any], provider: PaperlessProvider) -> None:
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
        shares = self._provider._get_shares()
        return list(shares.keys())

    def get_member(self, name: str) -> ShareResource | None:
        """Get a share by name.

        Args:
            name: The share name

        Returns:
            ShareResource if found, None otherwise
        """
        shares = self._provider._get_shares()
        if name in shares:
            share = shares[name]
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

    def _resolve_tag_ids_from_map(self, tag_map: dict[str, int], tag_names: list[str]) -> list[int]:
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

    def _get_tag_map(self, client: PaperlessClient) -> dict[str, int]:
        """Get tag name to ID mapping, using cache when possible.

        Args:
            client: The PaperlessClient to use for fetching tags

        Returns:
            Dict mapping tag names to tag IDs
        """
        token = self.environ.get("paperless.token", "")
        cache = get_cache()

        # Check cache first
        cached_map = cache.get_tag_map(token)
        if cached_map is not None:
            return cached_map

        # Fetch from API and cache
        all_tags = run_async(client.get_tags())
        tag_map = {tag.name: tag.id for tag in all_tags}
        cache.set_tag_map(token, tag_map)
        logger.debug("fetched_and_cached_tag_map", tag_count=len(tag_map))
        return tag_map

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
            # Get tag map (uses cache when available)
            tag_map = self._get_tag_map(client)

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
                done_tag_ids = self._resolve_tag_ids_from_map(tag_map, [self._share.done_tag])
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

            # Pre-fetch all document sizes concurrently
            prefetch_document_sizes(client, documents)

            return documents

        # Fall back to static mode
        return self._provider.get_documents_for_share(self._share.name)

    def _get_documents(self) -> list[PaperlessDocument]:
        """Get documents for this share, caching for the request.

        When multiple documents have the same sanitized filename,
        a warning is logged and the document ID is appended to disambiguate.
        The document with the LOWEST ID always gets the base filename to ensure
        deterministic behavior across requests.

        Returns:
            List of documents for this share
        """
        if self._loaded_documents is None:
            self._loaded_documents = self._load_documents()
            # Build filename index with collision detection
            # Sort by ID to ensure deterministic collision resolution
            self._doc_by_filename = {}
            for doc in sorted(self._loaded_documents, key=lambda d: d.id):
                base_name = sanitize_filename(doc.title)
                filename = f"{base_name}.pdf"
                if filename in self._doc_by_filename:
                    # Collision detected - append document ID to disambiguate
                    # The document with the lower ID keeps the base name
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
    ) -> DocumentResource | DoneFolderResource | MacOSMetadataResource | None:
        """Get a member resource by name.

        Args:
            name: The filename or folder name

        Returns:
            The appropriate resource, or None if not found
        """
        # Handle macOS metadata files - return virtual resource
        if is_macos_metadata_file(name):
            return MacOSMetadataResource(f"{self.path}/{name}", self.environ)

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

    def create_empty_resource(self, name: str) -> MacOSMetadataResource:
        """Create a new empty resource (for PUT to new file).

        Only allows creating macOS metadata files (._*, .DS_Store).
        Other files cannot be created (documents come from Paperless).

        Args:
            name: The filename to create

        Returns:
            MacOSMetadataResource for metadata files

        Raises:
            DAVError: 403 Forbidden if not a metadata file
        """
        if is_macos_metadata_file(name):
            logger.debug("create_empty_resource_metadata", path=f"{self.path}/{name}")
            return MacOSMetadataResource(f"{self.path}/{name}", self.environ)

        # Don't allow creating arbitrary files
        from wsgidav.dav_error import DAVError, HTTP_FORBIDDEN  # type: ignore[import-untyped]

        raise DAVError(HTTP_FORBIDDEN, f"Cannot create files in this share: {name}")


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

    def _resolve_tag_ids_from_map(self, tag_map: dict[str, int], tag_names: list[str]) -> list[int]:
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

    def _get_tag_map(self, client: PaperlessClient) -> dict[str, int]:
        """Get tag name to ID mapping, using cache when possible.

        Args:
            client: The PaperlessClient to use for fetching tags

        Returns:
            Dict mapping tag names to tag IDs
        """
        token = self.environ.get("paperless.token", "")
        cache = get_cache()

        # Check cache first
        cached_map = cache.get_tag_map(token)
        if cached_map is not None:
            return cached_map

        # Fetch from API and cache
        all_tags = run_async(client.get_tags())
        tag_map = {tag.name: tag.id for tag in all_tags}
        cache.set_tag_map(token, tag_map)
        logger.debug("fetched_and_cached_tag_map", tag_count=len(tag_map))
        return tag_map

    def _load_documents(self) -> list[PaperlessDocument]:
        """Load documents with done_tag from Paperless API.

        Returns:
            List of documents that have the done_tag
        """
        client = self._provider._create_client(self.environ)
        if client is not None:
            # Get tag map (uses cache when available)
            tag_map = self._get_tag_map(client)

            # Include tags: share's include_tags AND the done_tag
            # This ensures we only show documents that belong to this share
            # and are marked as done
            include_tag_ids = self._resolve_tag_ids_from_map(
                tag_map, list(self._share.include_tags)
            )

            # Add done_tag to include list (documents must have this tag)
            if self._share.done_tag:
                done_tag_ids = self._resolve_tag_ids_from_map(tag_map, [self._share.done_tag])
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

            # Pre-fetch all document sizes concurrently
            prefetch_document_sizes(client, documents)

            return documents

        # No client available - return empty list
        return []

    def _get_documents(self) -> list[PaperlessDocument]:
        """Get documents for this done folder, caching for the request.

        When multiple documents have the same sanitized filename,
        a warning is logged and the document ID is appended to disambiguate.
        The document with the LOWEST ID always gets the base filename to ensure
        deterministic behavior across requests.

        Returns:
            List of documents with done_tag
        """
        if self._loaded_documents is None:
            self._loaded_documents = self._load_documents()
            # Build filename index with collision detection
            # Sort by ID to ensure deterministic collision resolution
            self._doc_by_filename = {}
            for doc in sorted(self._loaded_documents, key=lambda d: d.id):
                base_name = sanitize_filename(doc.title)
                filename = f"{base_name}.pdf"
                if filename in self._doc_by_filename:
                    # Collision detected - append document ID to disambiguate
                    # The document with the lower ID keeps the base name
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

    def get_member(self, name: str) -> DocumentResource | MacOSMetadataResource | None:
        """Get a member by name.

        Args:
            name: The filename

        Returns:
            DocumentResource if found, MacOSMetadataResource for metadata files, None otherwise
        """
        # Handle macOS metadata files - return virtual resource
        if is_macos_metadata_file(name):
            return MacOSMetadataResource(f"{self.path}/{name}", self.environ)

        doc = self._get_doc_by_filename(name)
        if doc is not None:
            return DocumentResource(
                f"{self.path}/{name}",
                self.environ,
                self._provider,
                doc,
                share=self._share,
                in_done_folder=True,
            )
        return None

    def create_empty_resource(self, name: str) -> MacOSMetadataResource:
        """Create a new empty resource (for PUT to new file).

        Only allows creating macOS metadata files (._*, .DS_Store).

        Args:
            name: The filename to create

        Returns:
            MacOSMetadataResource for metadata files

        Raises:
            DAVError: 403 Forbidden if not a metadata file
        """
        if is_macos_metadata_file(name):
            logger.debug("create_empty_resource_metadata_done", path=f"{self.path}/{name}")
            return MacOSMetadataResource(f"{self.path}/{name}", self.environ)

        from wsgidav.dav_error import DAVError, HTTP_FORBIDDEN  # type: ignore[import-untyped]

        raise DAVError(HTTP_FORBIDDEN, f"Cannot create files in done folder: {name}")


class DocumentResource(DAVNonCollection):  # type: ignore[misc]
    """WebDAV resource representing a Paperless document.

    Exposes document metadata (dates, etag) and content as a PDF file.
    Supports move operations to/from done folder (adds/removes done_tag).
    """

    def __init__(
        self,
        path: str,
        environ: dict[str, Any],
        provider: PaperlessProvider,
        document: PaperlessDocument,
        share: Share | None = None,
        in_done_folder: bool = False,
    ) -> None:
        """Initialize the document resource.

        Args:
            path: The WebDAV path (e.g., "/share/document.pdf")
            environ: WSGI environ dictionary
            provider: The parent PaperlessProvider
            document: The PaperlessDocument metadata
            share: Optional Share configuration (needed for move operations)
            in_done_folder: Whether this document is located in the done folder
        """
        super().__init__(path, environ)
        self._provider = provider
        self.document = document
        self._share: Share | None = share
        self._in_done_folder: bool = in_done_folder
        # Cache for downloaded content
        self._content: bytes | None = None
        # Cache for file size (from HEAD request)
        self._file_size: int | None = None

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

        Uses a global cache to avoid re-downloading the same document.
        Also verifies and updates the size cache to ensure Content-Length
        consistency (HEAD requests may return different sizes than GET).

        Returns:
            Document content as bytes, or empty bytes on error
        """
        if self._content is not None:
            return self._content

        # Check global cache first
        cache = get_cache()
        cached_content = cache.get_content(self.document.id)
        if cached_content is not None:
            self._content = cached_content
            return self._content

        client = self._provider._create_client(self.environ)
        if client is not None:
            try:
                self._content = run_async(client.download_document(self.document.id))
                actual_size = len(self._content)

                # Check if cached size differs from actual size (HEAD vs GET mismatch)
                cached_size = cache.get_size(self.document.id)
                if cached_size is not None and cached_size != actual_size:
                    logger.warning(
                        "size_mismatch_corrected",
                        document_id=self.document.id,
                        cached_size=cached_size,
                        actual_size=actual_size,
                    )

                # Store in global cache (this also updates size cache)
                cache.set_content(self.document.id, self._content)
                logger.debug(
                    "downloaded_document_content",
                    document_id=self.document.id,
                    size=actual_size,
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

    def get_content_length(self) -> int | None:
        """Return the content length.

        Always downloads content if not already loaded to ensure the
        Content-Length matches the actual content that get_content() returns.
        This avoids mismatches where HEAD-derived cached sizes differ from
        actual GET content sizes.

        Returns:
            Content length in bytes, or None if unknown
        """
        # If we already have content loaded, use its size
        if self._content is not None:
            size = len(self._content)
            logger.info(
                "get_content_length_from_instance",
                document_id=self.document.id,
                size=size,
            )
            return size

        # Check if we have actual content cached (not just HEAD-derived size)
        cache = get_cache()
        cached_content = cache.get_content(self.document.id)
        if cached_content is not None:
            # Content is cached, so size is accurate
            self._content = cached_content
            size = len(self._content)
            logger.info(
                "get_content_length_from_cache",
                document_id=self.document.id,
                size=size,
            )
            return size

        # No content cached - download it to ensure accurate size
        # This is necessary because HEAD-derived sizes may differ from GET content
        content = self._download_content()
        size = len(content)
        logger.info(
            "get_content_length_downloaded",
            document_id=self.document.id,
            size=size,
        )
        return size

    def get_content(self) -> io.BytesIO:
        """Return the document content as a file-like object.

        Downloads the document content from Paperless API and returns
        it as a BytesIO stream.

        Returns:
            File-like object containing document content
        """
        content = self._download_content()
        logger.info(
            "get_content_returning",
            document_id=self.document.id,
            content_size=len(content),
        )
        return io.BytesIO(content)

    def get_creation_date(self) -> float:
        """Return the document creation date as Unix timestamp.

        Returns:
            The document's created timestamp as seconds since epoch
        """
        dt = self._parse_iso_datetime(self.document.created)
        return dt.timestamp()

    def get_last_modified(self) -> float:
        """Return the document modification date as Unix timestamp.

        Returns:
            The document's modified timestamp as seconds since epoch
        """
        dt = self._parse_iso_datetime(self.document.modified)
        return dt.timestamp()

    def get_etag(self) -> str:
        """Return an etag for cache validation.

        The etag is based on document ID and modification time,
        allowing clients to detect when documents have changed.

        Returns:
            A string etag value (wsgidav adds the quotes)
        """
        modified_ts = int(self._parse_iso_datetime(self.document.modified).timestamp())
        return f"{self.document.id}-{modified_ts}"

    def support_etag(self) -> bool:
        """Indicate whether this resource supports etags.

        Returns:
            True, as documents always have etags
        """
        return True

    def support_ranges(self) -> bool:
        """Indicate whether this resource supports Range requests.

        Returns:
            True, as documents support byte range requests
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
            True if the destination is inside the done folder AND document
            is not already in the done folder
        """
        if self._share is None:
            return False
        if not self._share.done_folder_enabled:
            return False
        # If already in done folder, no need to add tag again
        if self._in_done_folder:
            return False

        # Parse destination path: /{share_name}/{done_folder_name}/{filename}
        parts = [p for p in dest_path.split("/") if p]
        if len(parts) < 3:
            return False

        share_name = parts[0]
        folder_name = parts[1]

        # Check if it's moving to this share's done folder
        return share_name == self._share.name and folder_name == self._share.done_folder_name

    def _is_move_from_done_folder_to_root(self, dest_path: str) -> bool:
        """Check if this is a move from done folder to root.

        Args:
            dest_path: The destination path (e.g., "/inbox/Doc.pdf")

        Returns:
            True if moving from done folder to root (not to done folder)
        """
        if self._share is None:
            return False
        if not self._share.done_folder_enabled:
            return False
        if not self._in_done_folder:
            return False

        # Parse destination path: /{share_name}/{filename}
        parts = [p for p in dest_path.split("/") if p]
        if len(parts) != 2:
            return False

        share_name = parts[0]

        # Check if it's moving to this share's root (not to done folder)
        return share_name == self._share.name

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

    def _validate_move_destination(self, dest_path: str) -> None:
        """Validate that the move destination is allowed.

        Only these MOVE operations are allowed:
        - Root -> Done folder (within same share)
        - Done folder -> Root (within same share)
        - Same location moves (no-op, effectively a rename)

        Args:
            dest_path: The destination path

        Raises:
            DAVError: HTTP 403 Forbidden if the move is not allowed
        """
        # Import here to avoid circular import issues with wsgidav
        # (wsgidav.dav_error <-> wsgidav.util have circular dependencies)
        from wsgidav.dav_error import DAVError, HTTP_FORBIDDEN  # type: ignore[import-untyped]

        parts = [p for p in dest_path.split("/") if p]

        # Path must have 2 parts (share/file) or 3 parts (share/done/file)
        if len(parts) < 2 or len(parts) > 3:
            logger.warning(
                "move_invalid_path_structure",
                document_id=self.document.id,
                dest_path=dest_path,
                parts_count=len(parts),
            )
            raise DAVError(
                HTTP_FORBIDDEN,
                f"Move not allowed: invalid path structure '{dest_path}'",
            )

        dest_share_name = parts[0]

        # If we have share info, validate share matches
        if self._share is not None:
            if dest_share_name != self._share.name:
                logger.warning(
                    "move_cross_share_rejected",
                    document_id=self.document.id,
                    source_share=self._share.name,
                    dest_share=dest_share_name,
                    dest_path=dest_path,
                )
                raise DAVError(
                    HTTP_FORBIDDEN,
                    f"Move not allowed: cross-share moves not supported "
                    f"(from '{self._share.name}' to '{dest_share_name}')",
                )

            # If 3 parts, middle part must be the done folder
            if len(parts) == 3:
                folder_name = parts[1]
                if folder_name != self._share.done_folder_name:
                    logger.warning(
                        "move_invalid_subfolder",
                        document_id=self.document.id,
                        dest_path=dest_path,
                        folder_name=folder_name,
                        expected_done_folder=self._share.done_folder_name,
                    )
                    raise DAVError(
                        HTTP_FORBIDDEN,
                        f"Move not allowed: subdirectory moves not supported "
                        f"('{folder_name}' is not the done folder)",
                    )

    def handle_move(self, dest_path: str) -> bool:
        """Handle native MOVE operation.

        wsgidav calls this first to allow providers to handle moves natively.
        We return True and implement the move logic here to avoid the
        individual file copy/delete approach.

        Args:
            dest_path: The destination path

        Returns:
            True if handled, False to fall back to copy_move_single
        """
        from wsgidav.dav_error import DAVError, HTTP_FORBIDDEN  # type: ignore[import-untyped]

        logger.info(
            "handle_move_called",
            document_id=self.document.id,
            source_path=self.path,
            dest_path=dest_path,
        )

        # Validate the move destination
        try:
            self._validate_move_destination(dest_path)
        except DAVError:
            raise

        # Handle move TO done folder (add tag)
        if self._is_move_to_done_folder(dest_path):
            if self._handle_move_to_done_folder():
                return True
            raise DAVError(HTTP_FORBIDDEN, "Failed to move to done folder")

        # Handle move FROM done folder to root (remove tag)
        if self._is_move_from_done_folder_to_root(dest_path):
            if self._handle_move_from_done_folder():
                return True
            # Gracefully degrade if no client available (already logged)
            return False

        # No-op for other moves (same location)
        logger.debug(
            "move_no_tag_change",
            document_id=self.document.id,
            dest_path=dest_path,
        )
        return True

    def copy_move_single(self, dest_path: str, *, is_move: bool) -> bool:
        """Copy or move this document to dest_path.

        For our virtual filesystem, MOVE operations change tags:
        - Moving to done folder adds the done_tag
        - Moving from done folder removes the done_tag

        COPY operations are not supported (returns 403 Forbidden).

        Args:
            dest_path: The destination path
            is_move: True for MOVE, False for COPY

        Returns:
            True if successful

        Raises:
            DAVError: 403 Forbidden if operation is not allowed
        """
        from wsgidav.dav_error import DAVError, HTTP_FORBIDDEN  # type: ignore[import-untyped]

        logger.info(
            "copy_move_single_called",
            document_id=self.document.id,
            source_path=self.path,
            dest_path=dest_path,
            is_move=is_move,
        )

        # Only support MOVE, not COPY
        if not is_move:
            raise DAVError(HTTP_FORBIDDEN, "Copy not supported for documents")

        # Validate the move destination
        self._validate_move_destination(dest_path)

        # Handle move TO done folder (add tag)
        if self._is_move_to_done_folder(dest_path):
            if self._handle_move_to_done_folder():
                return True
            raise DAVError(HTTP_FORBIDDEN, "Failed to move to done folder")

        # Handle move FROM done folder to root (remove tag)
        if self._is_move_from_done_folder_to_root(dest_path):
            if self._handle_move_from_done_folder():
                return True
            # Gracefully degrade if no client available (already logged)
            return False

        # No-op for other moves (same location)
        logger.debug(
            "move_no_tag_change",
            document_id=self.document.id,
            dest_path=dest_path,
        )
        return True

    def _handle_move_to_done_folder(self) -> bool:
        """Handle move to done folder by adding the done_tag.

        Returns:
            True if successful, False if client unavailable
        """
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

    def _handle_move_from_done_folder(self) -> bool:
        """Handle move from done folder to root by removing the done_tag.

        Returns:
            True if successful, False if client unavailable
        """
        # Get the done_tag ID
        done_tag_id = self._get_done_tag_id()
        if done_tag_id is None:
            logger.warning(
                "done_tag_not_found_for_removal",
                document_id=self.document.id,
                done_tag=self._share.done_tag if self._share else None,
            )
            return True  # No-op if tag not found

        # Remove the done_tag from the document
        client = self._provider._create_client(self.environ)
        if client is None:
            logger.warning(
                "no_client_for_move_from_done",
                document_id=self.document.id,
            )
            return False

        try:
            run_async(client.remove_tag_from_document(self.document.id, done_tag_id))
            logger.info(
                "moved_from_done_folder",
                document_id=self.document.id,
                done_tag_id=done_tag_id,
            )
            return True
        except Exception as exc:
            logger.error(
                "move_from_done_folder_failed",
                document_id=self.document.id,
                done_tag_id=done_tag_id,
                error=str(exc),
            )
            return False

    def delete(self) -> None:
        """Handle deletion of document resource.

        For documents in the done folder, this removes the done_tag
        (making the document reappear in the share root).

        For documents not in the done folder, deletion is not allowed
        (we don't actually delete documents from Paperless).

        Raises:
            DAVError: 403 Forbidden if deletion is not allowed
        """
        from wsgidav.dav_error import DAVError, HTTP_FORBIDDEN  # type: ignore[import-untyped]

        # Only allow "deletion" from done folder (removes the done_tag)
        if self._in_done_folder:
            logger.info(
                "delete_from_done_folder",
                document_id=self.document.id,
            )
            # Removing the done_tag is the same as moving from done folder
            if self._handle_move_from_done_folder():
                return
            raise DAVError(HTTP_FORBIDDEN, "Failed to remove done tag")

        # Don't allow deletion from share root
        logger.warning(
            "delete_not_allowed",
            document_id=self.document.id,
            path=self.path,
        )
        raise DAVError(HTTP_FORBIDDEN, "Cannot delete documents from share root")
