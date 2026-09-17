"""Deterministic context budgeting, independent from prompts and HTTP transport."""

from dataclasses import dataclass

from .contracts import ContractError, require
from .context_models import ContextFragment


@dataclass(frozen=True)
class ContextAllocation:
    included: tuple[ContextFragment, ...]
    dropped_ids: tuple[str, ...]
    estimated_input_tokens: int
    input_token_limit: int
    reserved_output_tokens: int
    dropped: tuple[dict, ...] = ()
    estimator: str = "utf8_bytes_v1"

    def as_dict(self):
        return {
            "included": [item.id for item in self.included],
            "dropped": list(self.dropped_ids),
            "estimated_input_tokens": self.estimated_input_tokens,
            "input_token_limit": self.input_token_limit,
            "reserved_output_tokens": self.reserved_output_tokens,
            "drop_details": list(self.dropped),
            "estimator": self.estimator,
        }


def estimate_tokens(text):
    """A tokenizer-independent conservative estimate based on UTF-8 bytes."""
    require(isinstance(text, str), "token estimate input must be text")
    return max(1, len(text.encode("utf-8")))


def estimate_messages(messages):
    return sum(16 + estimate_tokens(message.get("content", "")) for message in messages)


class ContextAllocator:
    def allocate(
        self,
        base_messages,
        fragments,
        *,
        max_input_tokens,
        reserve_output_tokens,
        cost_fn=None,
    ):
        require(
            type(max_input_tokens) is int
            and type(reserve_output_tokens) is int
            and max_input_tokens > reserve_output_tokens > 0,
            "invalid context budget",
        )
        fragments = tuple(fragments)
        require(
            len({item.id for item in fragments}) == len(fragments),
            "context ids must be unique",
        )
        usable = max_input_tokens - reserve_output_tokens
        used = estimate_messages(base_messages)
        if used > usable:
            raise ContractError("method prompt exceeds model input budget")

        indexed = list(enumerate(fragments))
        required = sorted(
            ((i, item) for i, item in indexed if item.required),
            key=lambda pair: (-pair[1].priority, pair[1].id),
        )
        optional = sorted(
            ((i, item) for i, item in indexed if not item.required),
            key=lambda pair: (-pair[1].priority, pair[1].id),
        )
        selected = []
        dropped = []
        for _, item in required + optional:
            cost = (
                cost_fn(item)
                if cost_fn is not None
                else 24 + estimate_tokens(item.id) + estimate_tokens(str(item.content))
            )
            if used + cost <= usable:
                selected.append(item)
                used += cost
            elif item.required:
                raise ContractError(f"required context exceeds model input budget: {item.id}")
            else:
                dropped.append(item.id)
        return ContextAllocation(
            included=tuple(selected),
            dropped_ids=tuple(dropped),
            estimated_input_tokens=used,
            input_token_limit=max_input_tokens,
            reserved_output_tokens=reserve_output_tokens,
            dropped=tuple({"id": item_id, "reason": "over_budget"} for item_id in dropped),
        )


def context_message(fragments):
    """Compatibility wrapper; new calls should use RoleAwareRenderer."""
    from .context_render import RoleAwareRenderer

    if not fragments:
        return None
    messages = RoleAwareRenderer().render(fragments)
    require(len(messages) == 1, "context renders to multiple messages")
    return messages[0]
