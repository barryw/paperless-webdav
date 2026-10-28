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
    PaperlessUser,
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
    respx.get(f"{base_url}/api/tags/").mock(
        return_value=Response(200, json={"count": 0, "results": []})
    )

    result = await client.validate_token()

    assert result is True


@respx.mock
@pytest.mark.asyncio
async def test_validate_token_failure(client: PaperlessClient, base_url: str) -> None:
    """401 response returns False."""
    respx.get(f"{base_url}/api/tags/").mock(
        return_value=Response(401, json={"detail": "Invalid token"})
    )

    result = await client.validate_token()

    assert result is False


@respx.mock
@pytest.mark.asyncio
async def test_authorization_header(client: PaperlessClient, base_url: str) -> None:
    """Verify authorization header is sent correctly."""
    respx.get(f"{base_url}/api/tags/").mock(
        return_value=Response(200, json={"count": 0, "results": []})
    )

    await client.validate_token()

    assert len(respx.calls) == 1
    auth_header = respx.calls[0].request.headers.get("Authorization")
    assert auth_header == "Token test-api-token-12345"


# --- User Tests ---


@respx.mock
@pytest.mark.asyncio
async def test_get_users(client: PaperlessClient, base_url: str) -> None:
    """Should return users from Paperless API."""
    users_data = {
        "results": [
            {"id": 1, "username": "alice", "first_name": "Alice", "last_name": "Smith"},
            {"id": 2, "username": "bob", "first_name": "Bob", "last_name": "Jones"},
        ],
        "next": None,
    }
    respx.get(f"{base_url}/api/users/").mock(return_value=Response(200, json=users_data))

    users = await client.get_users()

    assert len(users) == 2
    assert users[0] == PaperlessUser(id=1, username="alice", first_name="Alice", last_name="Smith")
    assert users[1] == PaperlessUser(id=2, username="bob", first_name="Bob", last_name="Jones")


@respx.mock
@pytest.mark.asyncio
async def test_get_users_returns_empty_on_403(client: PaperlessClient, base_url: str) -> None:
    """Should return empty list when user lacks permission to list users."""
    respx.get(f"{base_url}/api/users/").mock(
        return_value=Response(403, json={"detail": "Permission denied"})
    )

    users = await client.get_users()

    assert users == []


@respx.mock
@pytest.mark.asyncio
async def test_search_users(client: PaperlessClient, base_url: str) -> None:
    """Search users by username filter."""
    respx.get(f"{base_url}/api/users/", params={"username__icontains": "ali"}).mock(
        return_value=Response(
            200,
            json={
                "results": [
                    {"id": 1, "username": "alice", "first_name": "Alice", "last_name": "Smith"},
                ],
                "next": None,
            },
        )
    )

    users = await client.search_users("ali")

    assert len(users) == 1
    assert users[0].username == "alice"


@respx.mock
@pytest.mark.asyncio
async def test_search_users_returns_empty_on_403(client: PaperlessClient, base_url: str) -> None:
    """Should return empty list when user lacks permission to search users."""
    respx.get(f"{base_url}/api/users/", params={"username__icontains": "ali"}).mock(
        return_value=Response(403, json={"detail": "Permission denied"})
    )

    users = await client.search_users("ali")

    assert users == []


@respx.mock
@pytest.mark.asyncio
async def test_get_users_handles_missing_names(client: PaperlessClient, base_url: str) -> None:
    """Should handle users with missing first/last names."""
    users_data = {
        "results": [
            {"id": 1, "username": "alice"},  # No first_name or last_name
        ],
        "next": None,
    }
    respx.get(f"{base_url}/api/users/").mock(return_value=Response(200, json=users_data))

    users = await client.get_users()

    assert len(users) == 1
    assert users[0] == PaperlessUser(id=1, username="alice", first_name="", last_name="")


# -----------------------------------------------------------------------------
# Document size probes -- regression coverage for upstream issue #3
# (PROPFIND used to download every document to compute Content-Length because
# the HEAD-based size disagreed with the served archive size.)
# -----------------------------------------------------------------------------


@respx.mock
@pytest.mark.asyncio
async def test_get_document_size_prefers_archive_size(
    client: PaperlessClient, base_url: str
) -> None:
    """Archive size is returned when both archive and original are present."""
    respx.get(f"{base_url}/api/documents/42/metadata/").mock(
        return_value=Response(
            200,
            json={"original_size": 765080, "archive_size": 1515552},
        )
    )

    size = await client.get_document_size(42)

    assert size == 1515552


@respx.mock
@pytest.mark.asyncio
async def test_get_document_size_falls_back_to_original_when_no_archive(
    client: PaperlessClient, base_url: str
) -> None:
    """When the document has no archive (e.g. PAPERLESS_OCR_SKIP_ARCHIVE_FILE
    skipped it), the served body is the original and original_size is correct."""
    respx.get(f"{base_url}/api/documents/7/metadata/").mock(
        return_value=Response(
            200,
            json={"original_size": 200000, "archive_size": None},
        )
    )

    size = await client.get_document_size(7)

    assert size == 200000


@respx.mock
@pytest.mark.asyncio
async def test_get_document_size_returns_none_on_failure(
    client: PaperlessClient, base_url: str
) -> None:
    """Errors are swallowed -- a failed probe is just a cache miss."""
    respx.get(f"{base_url}/api/documents/99/metadata/").mock(return_value=Response(500))

    size = await client.get_document_size(99)

    assert size is None


@respx.mock
@pytest.mark.asyncio
async def test_get_document_sizes_batch_populates_for_each_id(
    client: PaperlessClient, base_url: str
) -> None:
    """The batch probe issues one /metadata/ request per id and returns the
    served size for each that succeeded. This is what prefetch_document_sizes()
    relies on -- if it ever falls back to /download/ HEAD again, the size will
    be the smaller original-file size and get_content_length() will trigger a
    full re-download for every member during PROPFIND."""
    respx.get(f"{base_url}/api/documents/1/metadata/").mock(
        return_value=Response(200, json={"original_size": 100, "archive_size": 200})
    )
    respx.get(f"{base_url}/api/documents/2/metadata/").mock(
        return_value=Response(200, json={"original_size": 50, "archive_size": None})
    )
    respx.get(f"{base_url}/api/documents/3/metadata/").mock(return_value=Response(404))

    sizes = await client.get_document_sizes_batch([1, 2, 3])

    assert sizes == {1: 200, 2: 50}


@respx.mock
@pytest.mark.asyncio
async def test_get_document_sizes_batch_does_not_hit_download_endpoint(
    client: PaperlessClient, base_url: str
) -> None:
    """Regression: the batch probe must not touch /download/. If it does, the
    server is being asked to serve real archive bytes during PROPFIND, which is
    exactly the issue-#3 regression. Mock /download/ separately so any call
    counts toward this assertion."""
    download_route = respx.get(f"{base_url}/api/documents/1/download/").mock(
        return_value=Response(200, content=b"never-served")
    )
    respx.get(f"{base_url}/api/documents/1/metadata/").mock(
        return_value=Response(200, json={"original_size": 100, "archive_size": 200})
    )

    await client.get_document_sizes_batch([1])

    assert download_route.call_count == 0


def test_open_document_stream_yields_body_incrementally(
    client: PaperlessClient, base_url: str
) -> None:
    """open_document_stream returns a sync file-like that wsgidav can read
    in fixed-size blocks. This is the path the WEBDAV_STREAM_DOWNLOADS opt-in
    runs on the GET hot path; regressing it to a buffer-everything behaviour
    would re-introduce the ~15 s TTFB on 80 MB docs."""
    import respx as _respx
    from httpx import Response as _Response

    body = b"%PDF-1.4 " + b"a" * (200 * 1024) + b"\n%%EOF"
    with _respx.mock(assert_all_called=False) as router:
        router.get(f"{base_url}/api/documents/42/download/").mock(
            return_value=_Response(200, content=body)
        )
        stream = client.open_document_stream(42)
        try:
            first = stream.read(64 * 1024)
            assert len(first) == 64 * 1024
            assert first.startswith(b"%PDF-1.4 ")
            rest = stream.read()
            assert first + rest == body
        finally:
            stream.close()
