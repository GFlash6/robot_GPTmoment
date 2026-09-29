---
version: 1
slug: "ui-src-workbench-memory"
primary_target: "ui/src/Workbench.tsx"
related_targets: ["ui/src/workbench.css"]
---

# Workbench reference memory

Mode: Operate. Audience: local framework developers and robot operators. This brief covers only the reference-memory controls inside the existing Workbench session panel. It extends the established visual identity; no global DESIGN.md or design-system sidecar change applies.

## Direction contract

THESIS: Let an operator inspect scoped memory and explicitly bind its recorded version to the current session before requesting analysis or planning.

OWN-WORLD: Inherit the Workbench's muted green accents, light panels, typography, native forms, subtle separators and restrained rounded controls.

STORY: Read the scope and source caveat, search, inspect provenance, select records, bind them, then request fresh analysis and planning. Clear bindings when they are no longer relevant.

FIRST VIEWPORT: “参考记忆” sits inside “目标与上下文”, after the conversation turns. Search, selection and binding follow in reading order; the existing plan panel remains adjacent on wide screens and follows below on narrow screens.

FORM: A bounded local addition. Search, binding and clearing do not call the model. The existing explicit model actions remain separate.

## Implemented behavior

The introductory copy names the current robot namespace and limits retrieval to valid memories within that scope. It distinguishes verified source-file integrity from the truth or applicability of the text: operators must still judge the record against actual circumstances.

The surface shows the current binding count and, when populated, a native disclosure for “当前记忆引用与版本” plus “清除绑定记忆”. The labeled keyword input submits a trimmed query with the session's robot ID and a limit of ten results. Search is unavailable while disconnected, busy or empty. Starting a search clears the previous results and checkbox selection. An empty result has an explicit message; populated results announce both result and selection counts.

Each selectable row shows up to 240 characters, memory kind, verified source-file count and expiry status. “完整记忆与来源文件” discloses the full returned record and provenance. The checkbox label includes the excerpt, and the binding action stays disabled until at least one record is selected. The warning immediately before that action states that selection replaces the current bindings and invalidates existing goal analysis and plan drafts.

Binding submits record IDs and hashes with the session revision. Clearing submits an empty binding set. Both adopt the returned session and clear the visible draft, explanation and selection. Changing session identity also resets the search query, results, selection and explanation. These controls reuse the Workbench's pending status and alert presentation; they do not manufacture success states or automatically retry model calls.

## Established presentation and accessibility

The memory section uses a thin inherited border, 24px vertical margins and 20px top padding. Its heading is 16px, with the existing 14px Workbench body and 13px form/control text. Controls retain white backgrounds, green borders and 6px corners. Result rows use 12px vertical padding and understated separators; excerpts preserve whitespace and wrap long text.

Provenance disclosure labels use readable 12px dark green text (#40594d), with a minimum 32px summary height and 1.6 line height. The same scoped dark color applies to muted metadata and expanded provenance text. Keep this local contrast treatment rather than reverting memory provenance to the surrounding faint metadata style. Native disclosures and associated input labels preserve keyboard operation; search and checkbox focus use a visible accent outline. Binding counts, search counts and pending feedback use status semantics; errors use an alert.

Checkboxes remain 18px within a labeled row of at least 44px height. Action buttons retain the existing 40px minimum height. The inherited two-column Workbench stacks at 1000px and below; panel padding reduces to 16px at 700px and below. Controls and long source text must remain within the narrow panel, with all search, bind and clear actions reachable.

## Completion evidence and limits

The scoped finish review reported **ship** for provenance contrast and mobile controls. The recorded real-browser run in `docs/validation/memory-browser-live.json` reports passing empty search, bind/clear, no automatic model call, actual model context and plan path, worker hash verification, stale-draft invalidation and session isolation, with no mobile overflow or console errors. It records `qwen3.7-plus`, a succeeded worker execution, and matching output/evidence SHA-256 values; these are the recorded test results, not a new model call from this documentation pass.

The run's desktop and mobile screenshots are:

- `.runtime/memory-browser-validation/dbeb5d91-01aa-4b4f-a55d-531f5ed47898/desktop.png`
- `.runtime/memory-browser-validation/dbeb5d91-01aa-4b4f-a55d-531f5ed47898/mobile.png`

These are local validation captures, not shipping raster assets. This documentation pass inspected the component, stylesheet and recorded evidence; the brief makes no claim about unrelated Workbench surfaces or global accessibility conformance.
