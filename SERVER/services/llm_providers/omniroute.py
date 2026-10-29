import json
import time
import requests
from typing import Optional
from services.llm_providers.base import LLMProvider, LLMResult, ErrorCategory
from core.config import settings


class OmniRouteProvider(LLMProvider):
    def __init__(self):
        super().__init__(
            provider_name="OmniRoute",
            api_key=settings.OMNIROUTE_API_KEY,
            default_model="qwen/qwen3-32b"
        )

    def generate(self, prompt: str, user_content: str, model_override: Optional[str] = None) -> LLMResult:
        if not self.api_key:
            return LLMResult(
                success=False,
                error_msg="OmniRoute API Key not configured.",
                error_category=ErrorCategory.NON_RETRYABLE,
                provider_name=self.provider_name
            )

        model = model_override or self.default_model
        start = time.perf_counter()

        try:
            # OmniRoute router endpoint
            response = requests.post(
                url="https://api.omniroute.ai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                data=json.dumps({
                    "model": model,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {"role": "system", "content": prompt},
                        {"role": "user", "content": user_content}
                    ],
                    "temperature": 0.1
                }),
                timeout=settings.LLM_TIMEOUT_SECONDS
            )

            latency = round((time.perf_counter() - start) * 1000, 2)

            if response.status_code == 200:
                body = response.json()
                content = body['choices'][0]['message']['content'].strip()
                s_idx = content.find('{')
                e_idx = content.rfind('}')
                if s_idx != -1 and e_idx != -1:
                    clean_json = content[s_idx:e_idx + 1]
                    parsed = json.loads(clean_json)
                    return LLMResult(
                        success=True,
                        data=parsed,
                        provider_name=self.provider_name,
                        model_name=model,
                        latency_ms=latency
                    )
                else:
                    return LLMResult(
                        success=False,
                        error_msg="No JSON brackets found in OmniRoute response.",
                        error_category=ErrorCategory.INVALID_OUTPUT,
                        provider_name=self.provider_name,
                        model_name=model,
                        latency_ms=latency
                    )

            elif response.status_code in [429, 500, 502, 503, 504]:
                return LLMResult(
                    success=False,
                    error_msg=f"OmniRoute HTTP {response.status_code}: {response.text[:150]}",
                    error_category=ErrorCategory.PROVIDER_FAILURE,
                    provider_name=self.provider_name,
                    model_name=model,
                    latency_ms=latency
                )
            else:
                return LLMResult(
                    success=False,
                    error_msg=f"OmniRoute HTTP {response.status_code}: {response.text[:150]}",
                    error_category=ErrorCategory.NON_RETRYABLE,
                    provider_name=self.provider_name,
                    model_name=model,
                    latency_ms=latency
                )

        except requests.exceptions.Timeout:
            return LLMResult(
                success=False,
                error_msg="OmniRoute request timed out.",
                error_category=ErrorCategory.RETRYABLE,
                provider_name=self.provider_name,
                model_name=model
            )
        except Exception as e:
            return LLMResult(
                success=False,
                error_msg=f"OmniRoute network error: {str(e)}",
                error_category=ErrorCategory.RETRYABLE,
                provider_name=self.provider_name,
                model_name=model
            )
