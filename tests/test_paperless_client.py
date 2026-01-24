# tests/test_paperless_client.py
"""Tests for the Paperless-ngx API client."""

import json

import pytest
import respx
import structlog
from httpx import Response

from paperless_webdav.paperless_client import (
    PaperlessClient,
    PaperlessDocument,
    PaperlessTag,
)


@pytest.fixture(autouse=True)
def reset_structlog() -> None:
    """Reset structlog configuration for clean test isolation."""
    structlog.reset_defaults()


@pytest.fixture
def base_url() -> str:
    """Base URL for the Paperless API."""
    return "http://paperless.test"


@pytest.fixture
def api_token() -> str:
    """Test API token."""
    return "test-api-token-12345"


@pytest.fixture
def client(base_url: str, api_token: str) -> PaperlessClient:
    """Create a Paperless client instance."""
    return PaperlessClient(base_url=base_url, token=api_token)


@respx.mock
@pytest.mark.asyncio
async def test_get_tags(client: PaperlessClient, base_url: str) -> None:
    """Fetch and parse tags from the API."""
    respx.get(f"{base_url}/api/tags/").mock(
        return_value=Response(
            200,
            json={
                "count": 2,
                "next": None,
                "previous": None,
                "results": [
                    {"id": 1, "name": "invoice", "slug": "invoice"},
                    {"id": 2, "name": "receipt", "slug": "receipt"},
                ],
            },
        )
    )

    tags = await client.get_tags()

    assert len(tags) == 2
    assert tags[0] == PaperlessTag(id=1, name="invoice", slug="invoice")
    assert tags[1] == PaperlessTag(id=2, name="receipt", slug="receipt")


@respx.mock
@pytest.mark.asyncio
async def test_get_tags_with_pagination(client: PaperlessClient, base_url: str) -> None:
    """Fetch tags with pagination following next links."""
    call_count = 0

    def handle_tags_request(request: respx.MockRouter) -> Response:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # First page
            return Response(
                200,
                json={
                    "count": 3,
                    "next": f"{base_url}/api/tags/?page=2",
                    "previous": None,
                    "results": [
                        {"id": 1, "name": "invoice", "slug": "invoice"},
                    ],
                },
            )
        else:
            # Second page
            return Response(
                200,
                json={
                    "count": 3,
                    "next": None,
                    "previous": f"{base_url}/api/tags/",
                    "results": [
                        {"id": 2, "name": "receipt", "slug": "receipt"},
                        {"id": 3, "name": "tax", "slug": "tax"},
                    ],
                },
            )

    respx.get(url__startswith=f"{base_url}/api/tags/").mock(side_effect=handle_tags_request)

    tags = await client.get_tags()

    assert len(tags) == 3
    assert tags[0].name == "invoice"
    assert tags[1].name == "receipt"
    assert tags[2].name == "tax"


@respx.mock
@pytest.mark.asyncio
async def test_search_tags(client: PaperlessClient, base_url: str) -> None:
    """Search tags by name filter."""
    respx.get(f"{base_url}/api/tags/", params={"name__icontains": "inv"}).mock(
        return_value=Response(
            200,
            json={
                "count": 1,
                "next": None,
                "previous": None,
                "results": [
                    {"id": 1, "name": "invoice", "slug": "invoice"},
                ],
            },
        )
    )

    tags = await client.search_tags("inv")

    assert len(tags) == 1
    assert tags[0].name == "invoice"


@respx.mock
@pytest.mark.asyncio
async def test_get_documents_by_tags(client: PaperlessClient, base_url: str) -> None:
    """Fetch documents filtered by tags."""
    respx.get(
        f"{base_url}/api/documents/",
        params={"tags__id__all": "1,2", "tags__id__none": "3"},
    ).mock(
        return_value=Response(
            200,
            json={
                "count": 1,
                "next": None,
                "previous": None,
                "results": [
                    {
                        "id": 100,
                        "title": "Test Document",
                        "original_file_name": "test.pdf",
                        "created": "2024-01-15T10:30:00Z",
                        "modified": "2024-01-15T10:30:00Z",
                        "tags": [1, 2],
                    },
                ],
            },
        )
    )

    documents = await client.get_documents(include_tag_ids=[1, 2], exclude_tag_ids=[3])

    assert len(documents) == 1
    assert documents[0] == PaperlessDocument(
        id=100,
        title="Test Document",
        original_file_name="test.pdf",
        created="2024-01-15T10:30:00Z",
        modified="2024-01-15T10:30:00Z",
        tags=[1, 2],
    )


@respx.mock
@pytest.mark.asyncio
async def test_get_documents_no_filters(client: PaperlessClient, base_url: str) -> None:
    """Fetch all documents without filters."""
    respx.get(f"{base_url}/api/documents/").mock(
        return_value=Response(
            200,
            json={
                "count": 1,
                "next": None,
                "previous": None,
                "results": [
                    {
                        "id": 100,
                        "title": "Test Document",
                        "original_file_name": "test.pdf",
                        "created": "2024-01-15T10:30:00Z",
                        "modified": "2024-01-15T10:30:00Z",
                        "tags": [],
                    },
                ],
            },
        )
    )

    documents = await client.get_documents()

    assert len(documents) == 1


@respx.mock
@pytest.mark.asyncio
async def test_download_document(client: PaperlessClient, base_url: str) -> None:
    """Download PDF content for a document."""
    pdf_content = b"%PDF-1.4 fake pdf content"
    respx.get(f"{base_url}/api/documents/100/download/").mock(
        return_value=Response(
            200,
            content=pdf_content,
            headers={"Content-Type": "application/pdf"},
        )
    )

    content = await client.download_document(100)

    assert content == pdf_content


@respx.mock
@pytest.mark.asyncio
async def test_add_tag_to_document(client: PaperlessClient, base_url: str) -> None:
    """Add a tag to a document via PATCH."""
    # First get the document to know current tags
    respx.get(f"{base_url}/api/documents/100/").mock(
        return_value=Response(
            200,
            json={
                "id": 100,
                "title": "Test Document",
                "original_file_name": "test.pdf",
                "created": "2024-01-15T10:30:00Z",
                "modified": "2024-01-15T10:30:00Z",
                "tags": [1, 2],
            },
        )
    )
    # Then PATCH to add the new tag
    respx.patch(f"{base_url}/api/documents/100/").mock(
        return_value=Response(
            200,
            json={
                "id": 100,
                "title": "Test Document",
                "original_file_name": "test.pdf",
                "created": "2024-01-15T10:30:00Z",
                "modified": "2024-01-15T10:30:00Z",
                "tags": [1, 2, 3],
            },
        )
    )

    await client.add_tag_to_document(document_id=100, tag_id=3)

    # Verify the PATCH was called with the right data
    patch_call = [call for call in respx.calls if call.request.method == "PATCH"][0]
    patch_data = json.loads(patch_call.request.content)
    assert patch_data == {"tags": [1, 2, 3]}


@respx.mock
@pytest.mark.asyncio
async def test_remove_tag_from_document(client: PaperlessClient, base_url: str) -> None:
    """Remove a tag from a document via PATCH."""
    # First get the document to know current tags
    respx.get(f"{base_url}/api/documents/100/").mock(
        return_value=Response(
            200,
            json={
                "id": 100,
                "title": "Test Document",
                "original_file_name": "test.pdf",
                "created": "2024-01-15T10:30:00Z",
                "modified": "2024-01-15T10:30:00Z",
                "tags": [1, 2, 3],
            },
        )
    )
    # Then PATCH to remove the tag
    respx.patch(f"{base_url}/api/documents/100/").mock(
        return_value=Response(
            200,
            json={
                "id": 100,
                "title": "Test Document",
                "original_file_name": "test.pdf",
                "created": "2024-01-15T10:30:00Z",
                "modified": "2024-01-15T10:30:00Z",
                "tags": [1, 3],
            },
        )
    )

    await client.remove_tag_from_document(document_id=100, tag_id=2)

    # Verify the PATCH was called with the right data
    patch_call = [call for call in respx.calls if call.request.method == "PATCH"][0]
    patch_data = json.loads(patch_call.request.content)
    assert patch_data == {"tags": [1, 3]}


@respx.mock
@pytest.mark.asyncio
async def test_validate_token_success(client: PaperlessClient, base_url: str) -> None:
    """Valid token returns True."""
    respx.get(f"{base_url}/api/").mock(return_value=Response(200, json={}))

    result = await client.validate_token()

    assert result is True


@respx.mock
@pytest.mark.asyncio
async def test_validate_token_failure(client: PaperlessClient, base_url: str) -> None:
    """401 response returns False."""
    respx.get(f"{base_url}/api/").mock(
        return_value=Response(401, json={"detail": "Invalid token"})
    )

    result = await client.validate_token()

    assert result is False


@respx.mock
@pytest.mark.asyncio
async def test_authorization_header(client: PaperlessClient, base_url: str) -> None:
    """Verify authorization header is sent correctly."""
    respx.get(f"{base_url}/api/").mock(return_value=Response(200, json={}))

    await client.validate_token()

    assert len(respx.calls) == 1
    auth_header = respx.calls[0].request.headers.get("Authorization")
    assert auth_header == "Token test-api-token-12345"
