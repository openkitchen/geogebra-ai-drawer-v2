from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class LlmConfig:
    """Resolved runtime config for a single model invocation."""

    api_key: str = field(repr=False)
    base_url: str | None
    model: str
    temperature: float
    timeout_s: float


CapabilityTier = str  # "basic" | "standard" | "advanced" (kept loose to avoid import cycles)


@dataclass(frozen=True)
class RoleMetadata:
    name: str
    capability_tier: CapabilityTier
    preferred_for: tuple[str, ...] = ()


