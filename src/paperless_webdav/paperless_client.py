# src/paperless_webdav/paperless_client.py
"""Async HTTP client for the Paperless-ngx REST API."""

from dataclasses import dataclass
from typing import Any, cast

import httpx

from paperless_webdav.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class PaperlessTag:
    """Represents a tag in Paperless-ngx."""

    id: int
    name: str
    slug: str


@dataclass(frozen=True)
class PaperlessDocument:
    """Represents a document in Paperless-ngx."""

    id: int
    title: str
    original_file_name: str
    created: str
    modified: str
    tags: list[int]


class PaperlessClient:
    """Async client for the Paperless-ngx REST API.

    Uses token-based authentication and provides methods for:
    - Validating tokens
    - Fetching and searching tags
    - Fetching documents with tag filters
    - Downloading document content
    - Adding/removing tags from documents
    """

    def __init__(self, base_url: str, token: str) -> None:
        """Initialize the Paperless client.

        Args:
            base_url: Base URL of the Paperless-ngx instance (e.g., "http://paperless.local")
            token: API token for authentication
        """
        self.base_url = base_url.rstrip("/")
        self.token = token
        self._headers = {
            "Authorization": f"Token {token}",
            "Content-Type": "application/json",
        }

    async def _request(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
    ) -> httpx.Response:
        """Make an HTTP request to the Paperless API.

        Args:
            method: HTTP method (GET, POST, PATCH, etc.)
            endpoint: API endpoint path (e.g., "/api/tags/")
            params: Query parameters
            json_data: JSON body data

        Returns:
            httpx.Response object
        """
        url = f"{self.base_url}{endpoint}"
        async with httpx.AsyncClient() as client:
            response = await client.request(
                method=method,
                url=url,
                headers=self._headers,
                params=params,
                json=json_data,
            )
            return response

    async def _paginated_get(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch all pages of a paginated endpoint.

        Args:
            endpoint: API endpoint path
            params: Query parameters

        Returns:
            Combined list of all results from all pages
        """
        results: list[dict[str, Any]] = []
        url: str | None = f"{self.base_url}{endpoint}"
        request_params = params

        async with httpx.AsyncClient() as client:
            while url is not None:
                response = await client.get(
                    url,
                    headers=self._headers,
                    params=request_params,
                )
                response.raise_for_status()
                data = response.json()

                results.extend(data.get("results", []))

                # Get the next page URL
                url = data.get("next")
                # Only use params on the first request; next URL includes them
                request_params = None

        return results

    async def validate_token(self) -> bool:
        """Validate the API token by making a request to the API root.

        Returns:
            True if the token is valid, False if unauthorized
        """
        try:
            response = await self._request("GET", "/api/")
            if response.status_code == 401:
                logger.info("token_validation_failed", status_code=401)
                return False
            response.raise_for_status()
            logger.debug("token_validated")
            return True
        except httpx.HTTPStatusError as e:
            logger.warning("token_validation_error", error=str(e))
            return False

    async def get_tags(self) -> list[PaperlessTag]:
        """Fetch all tags from Paperless-ngx.

        Returns:
            List of PaperlessTag objects
        """
        results = await self._paginated_get("/api/tags/")
        tags = [
            PaperlessTag(
                id=tag["id"],
                name=tag["name"],
                slug=tag["slug"],
            )
            for tag in results
        ]
        logger.debug("fetched_tags", count=len(tags))
        return tags

    async def search_tags(self, name_filter: str) -> list[PaperlessTag]:
        """Search tags by name.

        Args:
            name_filter: Partial name to search for (case-insensitive)

        Returns:
            List of matching PaperlessTag objects
        """
        results = await self._paginated_get(
            "/api/tags/",
            params={"name__icontains": name_filter},
        )
        tags = [
            PaperlessTag(
                id=tag["id"],
                name=tag["name"],
                slug=tag["slug"],
            )
            for tag in results
        ]
        logger.debug("searched_tags", filter=name_filter, count=len(tags))
        return tags

    async def get_documents(
        self,
        include_tag_ids: list[int] | None = None,
        exclude_tag_ids: list[int] | None = None,
    ) -> list[PaperlessDocument]:
        """Fetch documents with optional tag filters.

        Args:
            include_tag_ids: List of tag IDs that documents must have (AND logic)
            exclude_tag_ids: List of tag IDs that documents must NOT have

        Returns:
            List of PaperlessDocument objects
        """
        params: dict[str, Any] = {}

        if include_tag_ids:
            params["tags__id__all"] = ",".join(str(tid) for tid in include_tag_ids)

        if exclude_tag_ids:
            params["tags__id__none"] = ",".join(str(tid) for tid in exclude_tag_ids)

        results = await self._paginated_get(
            "/api/documents/",
            params=params if params else None,
        )

        documents = [
            PaperlessDocument(
                id=doc["id"],
                title=doc["title"],
                original_file_name=doc["original_file_name"],
                created=doc["created"],
                modified=doc["modified"],
                tags=doc["tags"],
            )
            for doc in results
        ]
        logger.debug(
            "fetched_documents",
            count=len(documents),
            include_tags=include_tag_ids,
            exclude_tags=exclude_tag_ids,
        )
        return documents

    async def download_document(self, document_id: int) -> bytes:
        """Download the content of a document.

        Args:
            document_id: The ID of the document to download

        Returns:
            Raw bytes of the document content
        """
        response = await self._request("GET", f"/api/documents/{document_id}/download/")
        response.raise_for_status()
        logger.debug("downloaded_document", document_id=document_id, size=len(response.content))
        return response.content

    async def _get_document(self, document_id: int) -> dict[str, Any]:
        """Fetch a single document's details.

        Args:
            document_id: The ID of the document

        Returns:
            Document data as dictionary
        """
        response = await self._request("GET", f"/api/documents/{document_id}/")
        response.raise_for_status()
        return cast(dict[str, Any], response.json())

    async def add_tag_to_document(self, document_id: int, tag_id: int) -> None:
        """Add a tag to a document.

        Args:
            document_id: The ID of the document
            tag_id: The ID of the tag to add
        """
        # Get current tags
        doc = await self._get_document(document_id)
        current_tags: list[int] = doc.get("tags", [])

        if tag_id not in current_tags:
            new_tags = current_tags + [tag_id]
            response = await self._request(
                "PATCH",
                f"/api/documents/{document_id}/",
                json_data={"tags": new_tags},
            )
            response.raise_for_status()
            logger.info(
                "added_tag_to_document",
                document_id=document_id,
                tag_id=tag_id,
            )

    async def remove_tag_from_document(self, document_id: int, tag_id: int) -> None:
        """Remove a tag from a document.

        Args:
            document_id: The ID of the document
            tag_id: The ID of the tag to remove
        """
        # Get current tags
        doc = await self._get_document(document_id)
        current_tags: list[int] = doc.get("tags", [])

        if tag_id in current_tags:
            new_tags = [t for t in current_tags if t != tag_id]
            response = await self._request(
                "PATCH",
                f"/api/documents/{document_id}/",
                json_data={"tags": new_tags},
            )
            response.raise_for_status()
            logger.info(
                "removed_tag_from_document",
                document_id=document_id,
                tag_id=tag_id,
            )
