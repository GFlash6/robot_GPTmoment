"""Stateless HTTP transport for OpenAI-compatible chat-completions APIs."""

from dataclasses import dataclass
import json
import os
import time
from urllib.parse import urlparse

import httpx

from .contracts import ContractError, require


def environment_config():
    """Resolve the configured live model; never install a default model or token."""
    path = os.environ.get("ROBOT_AGENT_MODEL_CONFIG")
    if path:
        from pathlib import Path
        value = json.loads(Path(path).read_text())
    else:
        endpoint = os.environ.get("base_url") or os.environ.get("OPENAI_BASE_URL")
        model = os.environ.get("llm_model") or os.environ.get("OPENAI_MODEL")
        require(bool(endpoint) and bool(model), "model environment configuration missing")
        endpoint = endpoint.rstrip("/")
        if not endpoint.endswith("/chat/completions"):
            endpoint += "/chat/completions"
        token_env = "API_KEY" if os.environ.get("API_KEY") else "OPENAI_API_KEY"
        value = {"endpoint": endpoint, "model": model, "token_env": token_env, "timeout": 120}
    config = ModelConfig.from_mapping(value)
    require(bool(config.token_env) and bool(os.environ.get(config.token_env)), "live model API key missing")
    return value


@dataclass(frozen=True)
class ModelConfig:
    endpoint: str
    model: str
    token_env: str | None = None
    timeout: float = 60
    max_input_tokens: int = 32768
    max_output_tokens: int = 2048

    @classmethod
    def from_mapping(cls, value):
        require(isinstance(value, dict), "model config must be an object")
        endpoint = value.get("endpoint")
        model = value.get("model")
        require(
            isinstance(endpoint, str) and isinstance(model, str) and bool(model),
            "actual model endpoint and model ID required",
        )
        parsed = urlparse(endpoint)
        require(
            parsed.scheme in {"http", "https"}
            and parsed.hostname
            and not parsed.username
            and not parsed.password
            and not parsed.query
            and not parsed.fragment,
            "invalid model endpoint",
        )
        token_env = value.get("token_env")
        require(
            token_env is None or (isinstance(token_env, str) and bool(token_env)),
            "token_env must be a nonempty environment variable name",
        )
        timeout = value.get("timeout", 60)
        require(
            type(timeout) in {int, float} and timeout > 0,
            "model timeout must be positive",
        )
        max_input = value.get("max_input_tokens", 32768)
        max_output = value.get("max_output_tokens", 2048)
        require(
            type(max_input) is int
            and type(max_output) is int
            and max_input > max_output > 0,
            "model token limits must satisfy max_input_tokens > max_output_tokens > 0",
        )
        return cls(
            endpoint=endpoint,
            model=model,
            token_env=token_env,
            timeout=float(timeout),
            max_input_tokens=max_input,
            max_output_tokens=max_output,
        )


@dataclass(frozen=True)
class ModelRequest:
    messages: tuple[dict, ...]
    response_format: dict | None = None
    temperature: float | None = None


@dataclass(frozen=True)
class TransportResponse:
    status_code: int
    raw: str
    body: dict | None
    elapsed_ms: int


class ChatCompletionsTransport:
    """One request in, one response out; it owns no conversation state."""

    def send(self, config: ModelConfig, request: ModelRequest) -> TransportResponse:
        headers = {}
        if config.token_env:
            token = os.environ.get(config.token_env)
            require(bool(token), "model token environment variable missing")
            headers["Authorization"] = "Bearer " + token
        payload = {
            "model": config.model,
            "messages": list(request.messages),
            "max_tokens": config.max_output_tokens,
        }
        if request.response_format is not None:
            payload["response_format"] = request.response_format
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        started = time.monotonic()
        with httpx.Client(
            timeout=config.timeout, follow_redirects=False, trust_env=False
        ) as client:
            response = client.post(config.endpoint, json=payload, headers=headers)
        elapsed_ms = round((time.monotonic() - started) * 1000)
        try:
            body = response.json()
        except json.JSONDecodeError:
            body = None
        return TransportResponse(response.status_code, response.text, body, elapsed_ms)


class ModelCallError(ContractError):
    def __init__(self, message, response: TransportResponse | None = None):
        super().__init__(message)
        self.response = response
