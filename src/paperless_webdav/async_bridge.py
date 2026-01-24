"""Bridge utilities for running async code from sync contexts.

wsgidav is synchronous, but our Paperless client is async.
This module provides utilities to bridge the two.
"""

import asyncio
import concurrent.futures
from collections.abc import Coroutine
from typing import Any, TypeVar

T = TypeVar("T")


def run_async(coro: Coroutine[Any, Any, T]) -> T:
    """Run an async coroutine from a synchronous context.

    Creates a new event loop if none exists, or uses asyncio.run().
    This is safe to call from wsgidav request handlers.

    Args:
        coro: The coroutine to execute

    Returns:
        The result of the coroutine

    Raises:
        Any exception raised by the coroutine is propagated.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        # No running loop - create one
        return asyncio.run(coro)

    # If there's a running loop, we need to run in a new thread
    # This shouldn't happen in normal wsgidav usage, but handle it
    with concurrent.futures.ThreadPoolExecutor() as pool:
        future = pool.submit(asyncio.run, coro)
        return future.result()
