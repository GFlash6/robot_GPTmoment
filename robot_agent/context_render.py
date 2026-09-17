"""Render context according to authority without promoting external data."""

import json

from .context_models import ContextFragment
from .contracts import require


class RoleAwareRenderer:
    version = "role-aware-v1"

    def render_fragment(self, fragment: ContextFragment):
        if fragment.kind == "policy":
            require(
                fragment.authority == "framework",
                "only framework policy may use system authority",
            )
            return ({"role": "system", "content": self._text(fragment.content)},)

        if fragment.kind == "session":
            require(isinstance(fragment.content, list), "session context must be messages")
            messages = []
            for item in fragment.content:
                require(
                    isinstance(item, dict)
                    and item.get("role") in {"user", "assistant"}
                    and isinstance(item.get("content"), str),
                    "invalid session message",
                )
                messages.append({"role": item["role"], "content": item["content"]})
            return tuple(messages)

        envelope = {
            "context_id": fragment.id,
            "kind": fragment.kind,
            "source": fragment.source,
            "content": fragment.content,
        }
        return ({"role": "user", "content": json.dumps(envelope, ensure_ascii=False, sort_keys=True)},)

    def render(self, fragments):
        messages = []
        for fragment in fragments:
            messages.extend(self.render_fragment(fragment))
        return tuple(messages)

    @staticmethod
    def _text(content):
        return (
            content
            if isinstance(content, str)
            else json.dumps(content, ensure_ascii=False, sort_keys=True)
        )
