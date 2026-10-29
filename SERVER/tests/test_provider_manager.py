import pytest
from unittest.mock import MagicMock
from services.llm_providers.base import LLMProvider, LLMResult, ErrorCategory, ProviderHealth
from services.llm_providers.circuit_breaker import CircuitBreaker
from services.llm_providers.provider_manager import LLMProviderManager


class DummySuccessProvider(LLMProvider):
    def __init__(self, name="DummySuccess"):
        super().__init__(name, "dummy_key", "dummy-model")

    def generate(self, prompt: str, user_content: str, model_override=None) -> LLMResult:
        return LLMResult(
            success=True,
            data={"candidate_name": "Test Candidate", "score": 85},
            provider_name=self.provider_name,
            model_name=self.default_model,
            latency_ms=120.0
        )


class DummyFailureProvider(LLMProvider):
    def __init__(self, name="DummyFailure", category=ErrorCategory.PROVIDER_FAILURE):
        super().__init__(name, "dummy_key", "dummy-model")
        self.category = category

    def generate(self, prompt: str, user_content: str, model_override=None) -> LLMResult:
        return LLMResult(
            success=False,
            error_msg="HTTP 429 Rate Limit Simulated",
            error_category=self.category,
            provider_name=self.provider_name,
            model_name=self.default_model
        )


def test_provider_manager_level1_success():
    manager = LLMProviderManager()
    manager.providers = [DummySuccessProvider()]
    
    result = manager.execute_with_fallback("system prompt", "user content")
    assert result is not None
    assert result["candidate_name"] == "Test Candidate"
    assert "_llm_metadata" in result
    assert result["_llm_metadata"]["provider_used"] == "DummySuccess"
    assert result["_llm_metadata"]["status"] == "COMPLETED"


def test_provider_manager_failover_to_secondary():
    manager = LLMProviderManager()
    # Provider 1 fails with 429, Provider 2 succeeds
    manager.providers = [
        DummyFailureProvider("PrimaryProvider", ErrorCategory.PROVIDER_FAILURE),
        DummySuccessProvider("SecondaryProvider")
    ]

    result = manager.execute_with_fallback("system prompt", "user content")
    assert result is not None
    assert result["_llm_metadata"]["provider_used"] == "SecondaryProvider"
    assert result["_llm_metadata"]["fallback_used"] is True


def test_circuit_breaker_rate_limit_cooldown():
    cb = CircuitBreaker(rate_limit_cooldown=60.0)
    assert cb.is_available("ProviderA") is True
    
    cb.record_failure("ProviderA", ErrorCategory.PROVIDER_FAILURE)
    state = cb.get_state("ProviderA")
    assert state.health == ProviderHealth.RATE_LIMITED
    assert cb.is_available("ProviderA") is False


def test_level2_functionality_fallback():
    manager = LLMProviderManager()
    # All Level 1 providers fail
    manager.providers = [
        DummyFailureProvider("Provider1"),
        DummyFailureProvider("Provider2")
    ]

    result = manager.execute_with_fallback("system prompt", "user content")
    assert result is not None
    assert result["_llm_metadata"]["status"] == "MANUAL_REVIEW"
    assert result["_llm_metadata"]["provider_used"] == "Level 2 Deterministic Fallback"
    assert result["aicte_eligibility"]["primary_recommended_status"] == "Manual Review Required"
