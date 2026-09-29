# Model context evidence

Mode: Operate. Local extension of the existing model records page; inherit the established green/white observer UI. Context launcher already ran in this session; no new visual identity or raster assets.

## Direction contract

THESIS: An operator can identify which persisted context informed a selected real model record and see missing or inconsistent evidence.
OWN-WORLD: Existing observer panels, dark green readable text, native disclosure controls and restrained separators.
STORY: Select a model record, inspect the evidence status and included sources, expand actual content or budget exclusions.
FIRST VIEWPORT: Full-width evidence section below the current list/response pair; status and scope precede source details. On mobile it remains one column with wrapping IDs.
SIGNATURE INTERACTION: Native source disclosure preserves a compact scan of all included and excluded fragments. No decorative entrance motion or network mutations.
FORM: A narrow extension, not a new page or visual world; no concept seed or generated comp needed.
FINISH: Shipped. Independent finish review disposition: `ship`; no material fixes. All four browser captures are valid. The local Operate extension retains the incumbent visual identity. This surface contract records the result; global DESIGN.md is unchanged and no raster assets ship.

Boundary: document this surface only; preserve global design. No new DESIGN.md, assets, model calls or task controls. Verify actual HTTP ledger reads, record switching, real server disconnect/reconnect, copied-ledger corruption, and desktop/mobile behavior. No mock responses or synthetic screenshots.

## Shipped behavior

- `ui/src/ModelContext.tsx` and `ui/src/model-context.css`, integrated through `ui/src/App.tsx`, render a full-width evidence panel below the model list/response pair. The selected record drives the read-only `/models/{record_id}/context` request.
- Stored association/hash status and its scope appear before budget totals, source fragments, budget exclusions and raw diagnostics. Integrity covers stored links and the bundle hash only; it does not establish model correctness or robot task completion.
- Native disclosures expose persisted fragment content, authority, required/optional status, evidence IDs and metadata. Included fragments and recorded budget exclusions remain distinguishable; missing historical context is shown explicitly without reconstructing inputs.
- Loading, empty, unavailable, partial and inconsistent evidence states use text labels. Inconsistency is an alert. A failed refresh retains the selected record's last successful data with a stale-data notice; changing records clears unrelated evidence, and reconnecting recovers automatically.
- The panel inherits the observer's green/white surfaces, dark green text and restrained separators. Keyboard focus is visible; disclosure targets are at least 44px high. Budget fields wrap, long IDs/content wrap, and mobile spacing contracts below 700px without horizontal page overflow.

## Verification and provenance

- Frontend build passed; UI detector returned `[]`. Finish reviewer `/root/context_ui_review` returned `ship` with no material fixes.
- Browser evidence: `.runtime/context-browser-validation/87589858-1066-4434-88f1-84a119445cad/report.json`; durable validation summary: `docs/validation/context-browser-live.json`.
- Captures in that runtime directory: `desktop.png`, `mobile.png`, `desktop-context.png`, `mobile-context.png`. These are actual browser verification captures, not product assets or generated mockups.
- The passing browser run read eight existing real model records over HTTP and checked keyboard disclosure, model-switch isolation, legacy empty state, real server disconnect/restart, switching while disconnected, copied-ledger hash corruption, and desktop/mobile overflow.
- Reported zero new model calls, no mocks or simulation, no page errors and no browser mutations. After the isolated corruption check, the ledger hash exactly matched its initial value: `0f9d98489ad4d4de07d161b0b5ab5f0181f64888e0bf50a02fe664b826e9b166`.
