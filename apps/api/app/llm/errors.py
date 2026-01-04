from __future__ import annotations


class LlmError(Exception):
    """Base error for LLM-related operations."""


class LlmConfigError(LlmError):
    """Raised when LLM configuration is missing or invalid."""


class LlmInvocationError(LlmError):
    """Raised when an LLM invocation fails (network/provider/parse)."""


