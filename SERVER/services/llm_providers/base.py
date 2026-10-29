from abc import ABC, abstractmethod
from enum import Enum
from dataclasses import dataclass
from typing import Dict, Any, Optional


class ErrorCategory(str, Enum):
    RETRYABLE = "RETRYABLE"              # Transient network timeouts, socket drop
    NON_RETRYABLE = "NON_RETRYABLE"          # Invalid credentials, malformed request schema
    PROVIDER_FAILURE = "PROVIDER_FAILURE"     # HTTP 429 rate limit, 500, 502, 503, 504
    INVALID_OUTPUT = "INVALID_OUTPUT"       # JSON parse error, schema validation failure


class ProviderHealth(str, Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    RATE_LIMITED = "RATE_LIMITED"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass
class LLMResult:
    success: bool
    data: Optional[Dict[str, Any]] = None
    error_msg: str = ""
    error_category: Optional[ErrorCategory] = None
    provider_name: str = "Unknown"
    model_name: str = "Unknown"
    latency_ms: float = 0.0
    total_tokens: int = 0


class LLMProvider(ABC):
    """
    Common abstract LLM Interface. Every LLM provider independently implements this.
    """
    def __init__(self, provider_name: str, api_key: str, default_model: str):
        self.provider_name = provider_name
        self.api_key = api_key
        self.default_model = default_model

    @abstractmethod
    def generate(self, prompt: str, user_content: str, model_override: Optional[str] = None) -> LLMResult:
        """Synchronous / Async Generation interface contract."""
        pass
