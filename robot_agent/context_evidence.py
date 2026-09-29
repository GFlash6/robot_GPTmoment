"""Source and allocation evidence for a prepared call, without network or storage IO."""

from .context_models import ContextManifest


def context_manifest(bundle, prepared, renderer_version):
    included = {f.id for f in prepared.allocation.included}
    return ContextManifest(
        request_id=bundle.request.request_id, phase=bundle.request.phase,
        included=tuple(f.id for f in prepared.allocation.included),
        dropped=prepared.allocation.dropped,
        estimated_input_tokens=prepared.allocation.estimated_input_tokens,
        input_token_limit=prepared.allocation.input_token_limit,
        reserved_output_tokens=prepared.allocation.reserved_output_tokens,
        estimator=prepared.allocation.estimator, renderer_version=renderer_version,
        sources=tuple({"id": f.id, "source": f.source, "authority": f.authority,
                       "evidence_ids": list(f.evidence_ids), "metadata": f.metadata}
                      for f in prepared.allocation.included),
        provider_diagnostics=tuple({**d,
            "included": [fid for fid in d["fragment_ids"] if fid in included],
            "dropped": [item for item in prepared.allocation.dropped if item["id"] in d["fragment_ids"]],
        } for d in bundle.diagnostics),
    )
