import json
import time
import requests
from typing import Optional
from services.llm_providers.base import LLMProvider, LLMResult, ErrorCategory
from core.config import settings


class OpenRouterProvider(LLMProvider):
    def __init__(self):
        super().__init__(
            provider_name="OpenRouter",
            api_key=settings.OPENROUTER_API_KEY,
            default_model="qwen/qwen3-32b"
        )

    def generate(self, prompt: str, user_content: str, model_override: Optional[str] = None) -> LLMResult:
        if not self.api_key:
            return LLMResult(
                success=False,
                error_msg="OpenRouter API Key not configured.",
                error_category=ErrorCategory.NON_RETRYABLE,
                provider_name=self.provider_name
            )

        models_to_try = [model_override or self.default_model]
        fallback_models = [
            "meta-llama/llama-3.3-70b-instruct",
            "google/gemini-2.0-flash-exp:free",
            "qwen/qwen-2.5-72b-instruct",
            "meta-llama/llama-3.1-8b-instruct",
            "mistralai/mistral-small-24b-instruct-2501"
        ]
        for m in fallback_models:
            if m not in models_to_try:
                models_to_try.append(m)

        last_error = ""
        for current_model in models_to_try:
            start = time.perf_counter()
            try:
                response = requests.post(
                    url="https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    },
                    data=json.dumps({
                        "model": current_model,
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
                        
                        # Extract token usage
                        usage = body.get('usage', {})
                        tokens_used = usage.get('total_tokens', 0)
                        
                        return LLMResult(
                            success=True,
                            data=parsed,
                            provider_name=self.provider_name,
                            model_name=current_model,
                            latency_ms=latency,
                            total_tokens=tokens_used
                        )
                    else:
                        last_error = f"No JSON brackets in {current_model} response."

                elif response.status_code == 429:
                    last_error = f"OpenRouter model '{current_model}' rate limited (HTTP 429). Trying fallback model..."
                    print(f"OpenRouter Model '{current_model}' rate limited (429). Trying next fallback model...")
                    continue
                else:
                    last_error = f"OpenRouter HTTP {response.status_code} on model '{current_model}': {response.text[:100]}"
                    print(f"OpenRouter Model '{current_model}' failed with status {response.status_code}.")

            except requests.exceptions.Timeout:
                last_error = f"OpenRouter model '{current_model}' request timed out."
                continue
            except Exception as e:
                last_error = f"OpenRouter model '{current_model}' error: {str(e)}"
                continue

        return LLMResult(
            success=False,
            error_msg=last_error or "All OpenRouter fallback models exhausted.",
            error_category=ErrorCategory.PROVIDER_FAILURE,
            provider_name=self.provider_name,
            model_name=self.default_model
        )
