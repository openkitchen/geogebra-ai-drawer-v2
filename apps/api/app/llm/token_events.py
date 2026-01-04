"""Global token event manager for streaming LLM output.

This module provides a thread-safe way for graph nodes to send token events
that will be picked up by the SSE event generator in main.py.
"""

from __future__ import annotations

import threading
from collections import deque
from typing import Callable, TypedDict, Literal


TokenChannel = Literal["content", "reasoning", "meta"]


class TokenPayload(TypedDict, total=False):
    text_delta: str
    channel: TokenChannel


class TokenEventManager:
    """Thread-safe manager for token events per run_id."""
    
    def __init__(self):
        self._queues: dict[str, deque[str]] = {}
        self._callbacks: dict[str, Callable[[TokenPayload], None]] = {}
        self._lock = threading.Lock()
    
    def register_callback(self, run_id: str, callback: Callable[[TokenPayload], None]) -> None:
        """Register a callback for token events for a specific run_id."""
        with self._lock:
            self._callbacks[run_id] = callback
    
    def unregister_callback(self, run_id: str) -> None:
        """Unregister callback for a run_id."""
        with self._lock:
            self._callbacks.pop(run_id, None)
            self._queues.pop(run_id, None)
    
    def send_token(self, run_id: str, text_delta: str, *, channel: TokenChannel = "content") -> None:
        """Send a token event for a run_id.

        Args:
            text_delta: Text delta to stream
            channel: "content" (default), "reasoning" (dev-only), or "meta"
        """
        if not text_delta:
            return

        # IMPORTANT: do NOT call callback while holding the lock.
        # Callbacks may do slow work (e.g. cross-thread scheduling) and we don't want
        # to block other runs from registering/unregistering.
        callback: Callable[[TokenPayload], None] | None = None
        with self._lock:
            callback = self._callbacks.get(run_id)

        if callback:
            try:
                callback({"text_delta": text_delta, "channel": channel})
                return
            except Exception:
                # Fallback to queue if callback fails
                pass

        with self._lock:
            if run_id not in self._queues:
                self._queues[run_id] = deque()
            # Back-compat: queue only supports text deltas, keep content-only here.
            # (We intentionally avoid growing queue complexity; callbacks are expected in server mode.)
            self._queues[run_id].append(text_delta)
    
    def get_tokens(self, run_id: str) -> list[str]:
        """Get and clear all queued tokens for a run_id."""
        with self._lock:
            queue = self._queues.get(run_id)
            if not queue:
                return []
            tokens = list(queue)
            queue.clear()
            return tokens


# Global singleton instance
_token_manager = TokenEventManager()


def get_token_manager() -> TokenEventManager:
    """Get the global token event manager."""
    return _token_manager

