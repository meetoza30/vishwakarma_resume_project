import time
from typing import Dict
from services.llm_providers.base import ProviderHealth, ErrorCategory


class ProviderState:
    def __init__(self, name: str):
        self.name = name
        self.health: ProviderHealth = ProviderHealth.HEALTHY
        self.consecutive_failures: int = 0
        self.cooldown_until: float = 0.0


class CircuitBreaker:
    """
    Health-Aware Routing & Circuit Breaker Manager.
    Temporarily removes unhealthy/rate-limited providers from rotation.
    Automatically tests and re-enables them after a cooldown period.
    """
    def __init__(self, rate_limit_cooldown: float = 60.0, outage_cooldown: float = 120.0):
        self.rate_limit_cooldown = rate_limit_cooldown
        self.outage_cooldown = outage_cooldown
        self.states: Dict[str, ProviderState] = {}

    def get_state(self, provider_name: str) -> ProviderState:
        if provider_name not in self.states:
            self.states[provider_name] = ProviderState(provider_name)
        return self.states[provider_name]

    def is_available(self, provider_name: str) -> bool:
        state = self.get_state(provider_name)
        now = time.time()
        
        # If in cooldown, check if cooldown timer expired
        if state.health in [ProviderHealth.RATE_LIMITED, ProviderHealth.UNAVAILABLE]:
            if now >= state.cooldown_until:
                print(f"Cooldown timer expired for '{provider_name}'. Testing provider (DEGRADED probe)...")
                state.health = ProviderHealth.DEGRADED
                return True
            return False
            
        return True

    def record_success(self, provider_name: str):
        state = self.get_state(provider_name)
        state.consecutive_failures = 0
        state.health = ProviderHealth.HEALTHY

    def record_failure(self, provider_name: str, category: ErrorCategory):
        state = self.get_state(provider_name)
        state.consecutive_failures += 1
        now = time.time()

        if category == ErrorCategory.PROVIDER_FAILURE:
            print(f"Provider '{provider_name}' rate limited / outage. Initiating {self.rate_limit_cooldown}s circuit breaker cooldown.")
            state.health = ProviderHealth.RATE_LIMITED
            state.cooldown_until = now + self.rate_limit_cooldown
        elif state.consecutive_failures >= 3:
            print(f"Provider '{provider_name}' failed 3 consecutive attempts. Marking UNAVAILABLE for {self.outage_cooldown}s.")
            state.health = ProviderHealth.UNAVAILABLE
            state.cooldown_until = now + self.outage_cooldown
        else:
            state.health = ProviderHealth.DEGRADED


circuit_breaker = CircuitBreaker()
