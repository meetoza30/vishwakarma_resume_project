import time
import random
from typing import Dict, Any, List
from services.llm_providers.base import LLMProvider, LLMResult, ErrorCategory
from services.llm_providers.circuit_breaker import circuit_breaker
from services.llm_providers.openrouter import OpenRouterProvider
from services.llm_providers.nvidia_nim import NvidiaNimProvider
from services.llm_providers.omniroute import OmniRouteProvider
from services.llm_providers.groq import GroqProvider
from services.llm_providers.deepinfra import DeepInfraProvider
from services.llm_providers.nebius import NebiusProvider
from services.aicte_engine import evaluate_aicte_eligibility


class LLMProviderManager:
    """
    Master Multi-Provider LLM Fallback Engine.
    Implements Level 1 API failovers (OpenRouter -> NVIDIA NIM -> OmniRoute -> Groq -> DeepInfra -> Nebius)
    and Level 2 Functionality failovers (Deterministic Processing -> Manual Review).
    """
    def __init__(self):
        # Priority order of Level 1 Providers
        self.providers: List[LLMProvider] = [
            OpenRouterProvider(),
            NvidiaNimProvider(),
            OmniRouteProvider(),
            GroqProvider(),
            DeepInfraProvider(),
            NebiusProvider(),
        ]

    def execute_with_fallback(self, prompt: str, user_content: str) -> Dict[str, Any]:
        start_time = time.perf_counter()
        total_attempts = 0
        fallback_used = False
        last_error_msg = ""

        # Level 1 — API / Provider Fallback Chain
        for provider_idx, provider in enumerate(self.providers):
            # Check circuit breaker health
            if not circuit_breaker.is_available(provider.provider_name):
                print(f"Skipping provider '{provider.provider_name}' (Circuit Breaker Cooldown Active).")
                fallback_used = True
                continue

            if provider_idx > 0:
                fallback_used = True

            max_retries = 2
            for attempt in range(max_retries):
                total_attempts += 1
                print(f"Level 1 LLM Execution: Provider='{provider.provider_name}' (Attempt {attempt+1}/{max_retries})...")
                
                result: LLMResult = provider.generate(prompt, user_content)

                if result.success and result.data:
                    # Success: record circuit breaker recovery
                    circuit_breaker.record_success(provider.provider_name)
                    
                    elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
                    
                    # Attach processing metadata
                    result.data["_llm_metadata"] = {
                        "provider_used": result.provider_name,
                        "model_used": result.model_name,
                        "attempts": total_attempts,
                        "fallback_used": fallback_used,
                        "processing_time_ms": elapsed_ms,
                        "total_tokens": result.total_tokens,
                        "status": "COMPLETED"
                    }
                    
                    print(f"LLM Success! Provider={result.provider_name} Model={result.model_name} Time={elapsed_ms}ms Tokens={result.total_tokens} (Fallback={fallback_used})")
                    return result.data

                # Handle failure categories
                last_error_msg = result.error_msg
                category = result.error_category or ErrorCategory.PROVIDER_FAILURE
                print(f"Provider '{provider.provider_name}' failed ({category.value}): {result.error_msg}")

                if category == ErrorCategory.NON_RETRYABLE:
                    # Invalid key or bad configuration -> don't retry, failover to next provider immediately
                    circuit_breaker.record_failure(provider.provider_name, category)
                    break

                elif category in [ErrorCategory.RETRYABLE, ErrorCategory.PROVIDER_FAILURE]:
                    # Retry with exponential backoff + random jitter
                    circuit_breaker.record_failure(provider.provider_name, category)
                    if attempt < max_retries - 1:
                        backoff = (2 ** attempt) + random.uniform(0.1, 0.5)
                        print(f"Retrying '{provider.provider_name}' in {backoff:.2f}s (jittered backoff)...")
                        time.sleep(backoff)

        # Level 2 — Functionality Fallback
        print(f"Level 1 API Fallback Exhausted across all providers. Initiating Level 2 Functionality Fallback...")
        elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)

        # Safe Deterministic Fallback Payload for Manual Review
        fallback_candidate_data = {
            "sr_no": 1,
            "candidate_name": "Unprocessed Candidate (Manual Review Required)",
            "contact_number": "Not Mentioned",
            "email_id": "Not Mentioned",
            "qualification": {
                "ug": {"degree": "Not Mentioned"},
                "pg": {"degree": "Not Mentioned"},
                "phd": {"status": "None"},
                "formatted_string": "Extracted via Level 2 Fallback"
            },
            "scopus_post_phd_publications": 0,
            "patents": "Nil",
            "grants_funding": "Nil",
            "experience": {"total_years": 0.0, "details": "Teaching: 0 Yrs, Industry: 0 Yrs"},
            "previous_employers": [],
            "extra_academic_fields": {},
            "_llm_metadata": {
                "provider_used": "Level 2 Deterministic Fallback",
                "model_used": "None",
                "attempts": total_attempts,
                "fallback_used": True,
                "processing_time_ms": elapsed_ms,
                "total_tokens": 0,
                "status": "MANUAL_REVIEW",
                "last_error": last_error_msg
            }
        }

        # Run AICTE Rule Engine on fallback candidate data
        fallback_candidate_data["aicte_eligibility"] = evaluate_aicte_eligibility(fallback_candidate_data)
        fallback_candidate_data["aicte_eligibility"]["primary_recommended_status"] = "Manual Review Required"
        fallback_candidate_data["aicte_eligibility"]["verification_status"] = "Flagged for Manual Review"

        return fallback_candidate_data


# Global Provider Manager Instance
provider_manager = LLMProviderManager()
