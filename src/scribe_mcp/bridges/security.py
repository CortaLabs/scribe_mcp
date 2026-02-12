"""Security utilities for bridge operations."""

import asyncio
import functools
import logging
from typing import Callable, Any, TypeVar, Optional

logger = logging.getLogger(__name__)

T = TypeVar('T')


class BridgeSecurityManager:
    """
    Security utilities for isolating bridge failures.

    Provides timeout enforcement and error isolation to prevent
    bridge failures from affecting Scribe core operations.
    """

    @staticmethod
    async def execute_with_timeout(
        func: Callable,
        timeout_ms: int,
        *args,
        **kwargs
    ) -> Any:
        """
        Execute async function with timeout.

        Args:
            func: Async function to execute
            timeout_ms: Timeout in milliseconds
            *args, **kwargs: Arguments to pass to function

        Returns:
            Function result

        Raises:
            asyncio.TimeoutError: If function exceeds timeout
        """
        return await asyncio.wait_for(
            func(*args, **kwargs),
            timeout=timeout_ms / 1000.0
        )

    @staticmethod
    def isolate_errors(func: Callable) -> Callable:
        """
        Decorator to catch and log all exceptions.

        Errors are logged but not propagated, returning None instead.

        Args:
            func: Async function to wrap

        Returns:
            Wrapped function that isolates errors
        """
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                logger.error(f"Isolated error in {func.__name__}: {e}")
                return None
        return wrapper

    @staticmethod
    async def safe_execute(
        func: Callable,
        timeout_ms: int,
        default: Any = None,
        *args,
        **kwargs
    ) -> Any:
        """
        Execute function with timeout and error isolation.

        Returns default value on any error or timeout.

        Args:
            func: Async function to execute
            timeout_ms: Timeout in milliseconds
            default: Default value to return on error
            *args, **kwargs: Arguments to pass to function

        Returns:
            Function result or default value
        """
        try:
            return await asyncio.wait_for(
                func(*args, **kwargs),
                timeout=timeout_ms / 1000.0
            )
        except asyncio.TimeoutError:
            logger.error(f"Safe execute timed out after {timeout_ms}ms")
            return default
        except Exception as e:
            logger.error(f"Safe execute failed: {e}")
            return default
