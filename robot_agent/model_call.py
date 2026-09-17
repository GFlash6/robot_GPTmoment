"""Reusable model-call block composing method, context allocation, and transport."""

from dataclasses import dataclass

from .contracts import require
from .context_render import RoleAwareRenderer
from .model_context import ContextAllocator, estimate_messages
from .model_methods import DEFAULT_METHODS
from .model_transport import (
    ChatCompletionsTransport,
    ModelCallError,
    ModelConfig,
    ModelRequest,
    TransportResponse,
)


@dataclass(frozen=True)
class ModelCallResult:
    method: str
    content: str
    response_id: str | None
    actual_model: str | None
    finish_reason: str
    allocation: object
    transport: TransportResponse


@dataclass(frozen=True)
class PreparedModelCall:
    method: str
    request: ModelRequest
    allocation: object


class ModelCaller:
    """Safe to share between threads: each call keeps all mutable state local."""

    def __init__(self, config, *, methods=None, allocator=None, transport=None, renderer=None):
        self.config = (
            config if isinstance(config, ModelConfig) else ModelConfig.from_mapping(config)
        )
        self._methods = dict(methods or DEFAULT_METHODS)
        self._allocator = allocator or ContextAllocator()
        self._transport = transport or ChatCompletionsTransport()
        self._renderer = renderer or RoleAwareRenderer()

    def prepare(self, method, arguments, *, context=()):
        require(method in self._methods, f"unknown model call method: {method}")
        prompt = self._methods[method].prepare(arguments)
        allocation = self._allocator.allocate(
            prompt.base_messages,
            context,
            max_input_tokens=self.config.max_input_tokens,
            reserve_output_tokens=self.config.max_output_tokens,
            cost_fn=lambda fragment: estimate_messages(
                self._renderer.render_fragment(fragment)
            ),
        )
        messages = list(prompt.system_messages)
        messages.extend(self._renderer.render(allocation.included))
        messages.append(prompt.user_message)
        request = ModelRequest(
            messages=tuple(messages),
            response_format=prompt.response_format,
            temperature=prompt.temperature,
        )
        return PreparedModelCall(method=method, request=request, allocation=allocation)

    def send_prepared(self, prepared):
        try:
            response = self._transport.send(self.config, prepared.request)
        except Exception as exc:
            if isinstance(exc, ModelCallError):
                raise
            raise ModelCallError(f"model transport failed: {type(exc).__name__}") from exc
        if not 200 <= response.status_code < 300:
            raise ModelCallError(f"model HTTP status {response.status_code}", response)
        body = response.body
        if not (
            isinstance(body, dict)
            and isinstance(body.get("choices"), list)
            and body["choices"]
        ):
            raise ModelCallError("missing model choices", response)
        choice = body["choices"][0]
        if choice.get("finish_reason") != "stop":
            raise ModelCallError("model response incomplete or refused", response)
        message = choice.get("message", {})
        if message.get("refusal"):
            raise ModelCallError("model refused request", response)
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise ModelCallError("empty model response", response)
        return ModelCallResult(
            method=prepared.method,
            content=content,
            response_id=body.get("id"),
            actual_model=body.get("model"),
            finish_reason=choice["finish_reason"],
            allocation=prepared.allocation,
            transport=response,
        )

    def call(self, method, arguments, *, context=()):
        return self.send_prepared(self.prepare(method, arguments, context=context))
