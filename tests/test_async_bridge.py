"""Tests for async/sync bridge utilities."""

import asyncio
import pytest
from paperless_webdav.async_bridge import run_async


def test_run_async_returns_result():
    """run_async should execute coroutine and return result."""

    async def coro():
        return "hello"

    result = run_async(coro())
    assert result == "hello"


def test_run_async_propagates_exceptions():
    """run_async should propagate exceptions from coroutine."""

    async def failing_coro():
        raise ValueError("test error")

    with pytest.raises(ValueError, match="test error"):
        run_async(failing_coro())


def test_run_async_works_from_sync_context():
    """run_async should work when no event loop is running."""

    async def fetch_data():
        await asyncio.sleep(0.001)
        return {"data": 42}

    result = run_async(fetch_data())
    assert result == {"data": 42}


def test_run_async_with_awaited_operations():
    """run_async should handle coroutines with multiple await points."""

    async def multi_await():
        await asyncio.sleep(0.001)
        result = await asyncio.sleep(0.001, result="intermediate")
        await asyncio.sleep(0.001)
        return f"completed with {result}"

    result = run_async(multi_await())
    assert result == "completed with intermediate"


def test_run_async_from_existing_loop():
    """run_async should work when called from within an existing event loop.

    This tests the thread pool fallback when an event loop is already running.
    """
    results = []

    async def inner_coro():
        return "from inner"

    async def outer_coro():
        # This simulates being called from within an async context
        # run_async should detect the running loop and use thread pool
        result = run_async(inner_coro())
        results.append(result)

    # Run the outer coroutine which will call run_async
    asyncio.run(outer_coro())

    assert results == ["from inner"]


def test_run_async_propagates_custom_exception():
    """run_async should propagate custom exceptions with their attributes."""

    class CustomError(Exception):
        def __init__(self, message, code):
            super().__init__(message)
            self.code = code

    async def raise_custom():
        raise CustomError("custom error", code=42)

    with pytest.raises(CustomError) as exc_info:
        run_async(raise_custom())

    assert str(exc_info.value) == "custom error"
    assert exc_info.value.code == 42
