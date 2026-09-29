"""Assemble trusted providers; budget and role rendering remain separate stages."""
from dataclasses import replace
from copy import deepcopy
from .context_models import ContextBundle, ContextRequest, ContextFragment
from .context_providers import DEFAULT_PROVIDERS, ProviderInput, capabilities, task_state
from .contracts import require


class ContextBuilder:
    def __init__(self, store, *, providers=None):
        self.store = store
        self.providers = tuple(DEFAULT_PROVIDERS if providers is None else providers)
        names = [provider.name for provider in self.providers]
        require(all(isinstance(name, str) and name for name in names), "context provider name required")
        require(len(set(names)) == len(names), "duplicate context provider name")

    # Kept for callers preparing the same capability and task views for budgeting.
    capabilities = staticmethod(capabilities)
    task_state = staticmethod(task_state)

    def build(self, request: ContextRequest, catalog, *, session_override=None):
        require(isinstance(catalog, dict), "skill catalog required")
        require(not request.context_snapshot_id or request.session_id, "snapshot requires a session")
        require(session_override is None or request.session_id, "session override requires a session")
        session = None
        if request.session_id:
            snapshot = None
            if request.context_snapshot_id:
                from .context_snapshot import read_snapshot
                snapshot = read_snapshot(self.store, request.context_snapshot_id,
                                         robot_id=request.robot_id, session_id=request.session_id)
                require(snapshot["goal"] == request.goal.as_dict(), "planning snapshot request goal mismatch")
            require(not (snapshot and session_override is not None), "cannot override an immutable context snapshot")
            session = snapshot["session"] if snapshot else (session_override if session_override is not None else self.store.get("sessions", request.session_id))
            require(session is not None and session["robot_id"] == request.robot_id, "invalid context session")
            require(session["id"] == request.session_id, "context session mismatch")
        inputs = deepcopy(ProviderInput(request=request, catalog=catalog, session=session))
        fragments, diagnostics = [], []
        for provider in self.providers:
            isolated = deepcopy(inputs)
            result = provider.collect(self.store, isolated)
            require(isolated == inputs, f"context provider modified its input: {provider.name}")
            require(isinstance(result, tuple) and all(isinstance(f, ContextFragment) for f in result),
                    "invalid context provider result")
            result = deepcopy(result)
            fragments.extend(replace(f, metadata={**f.metadata, "provider": provider.name,
                                                 "provider_contract_version": 1}) for f in result)
            diagnostics.append({"provider": provider.name, "status": "collected" if result else "empty",
                                "fragment_ids": [f.id for f in result]})
        return ContextBundle(request=deepcopy(inputs.request), fragments=tuple(fragments), diagnostics=tuple(diagnostics))
