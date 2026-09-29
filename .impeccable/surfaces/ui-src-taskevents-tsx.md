# Task events

Mode: Operate. Narrow extension of the existing workbench. No replacement visual world or shipping raster assets.

## Direction contract

THESIS: Operators follow actual task history with bounded reads and explicit stale state.
OWN-WORLD: Existing workbench panels, muted green controls, native selector, compact disclosure rows.
STORY: Choose a permitted task, read ordered evidence, load another page or recover from a disconnection.
FIRST VIEWPORT: Full-width panel below planning, title and task selector above a chronological list; details stay collapsed.
FORM: Existing workbench extension; seed not applicable to this preserved layout.
FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance

Boundary: preserve existing global design; document this surface only. No new DESIGN.md needed for this extension. Endpoint is task.events-page; polling must never invoke a model or mutation.

## Implemented surface

The full-width “任务事件记录” panel follows the planning columns and appears only with an active connection and access to `task.events-page`. It inherits the Workbench's muted green controls and panel treatment. The native task selector leads to the full task ID, read controls, event count, and chronological rows. Each row shows the event type, actual sequence and local timestamp; “查看事件证据” reveals the original JSON through the existing disclosure component.

The heading is 18px, body and selector 14px, and disclosure labels and JSON 13px. Selector and evidence text use dark green (#263c32); secondary sequence/time text uses #40594d. Selector and disclosure targets have a 44px minimum height. Existing Workbench buttons retain their inherited styling. Panel padding is 24px, reduced to 16px at widths up to 800px; rows use 16px vertical padding and pale separators (#dce5df). Task IDs wrap and event headers can wrap on narrow screens.

**The evidence rule.** Preserve original event data and distinguish command requests, execution records, and task outcomes. An event or model response alone does not establish robot goal completion.

**The bounded read rule.** Read 50 events per page under a fixed `through_seq`; wait for “加载后续事件” while more pages remain. After the round is complete, query increments every 2.5 seconds. Refreshing or disclosing evidence must not call a model or control a task.

**The retained history rule.** Validate task identity, increasing sequences, page bounds, and cursor progress before committing a page. Errors retain the last successful records with a visible alert and retry control. Task switches discard late results from the previous selection; credential changes disconnect and unmount the event view. Empty, loading, list failure, and event failure states remain explicit. Global sequence gaps are legitimate and must not be treated as missing task events.

## Validation and provenance

Sources: `ui/src/TaskEvents.tsx`, `ui/src/Workbench.tsx`, `ui/src/workbench.css`, `PRODUCT.md`, and `docs/EVENT_PAGES.md`.

Browser evidence lives in `.runtime/event-browser-validation/f773965b-68fc-468b-9401-a20e5c8b2aad/`: `report.json`, final `recapture.json`, and final `desktop.png` / `mobile.png`. The recapture confirms disclosure and JSON computed styles at 13px and rgb(38, 60, 50). Final reviewer disposition: **ship**, scoped to the event surface readability fixes and existing Workbench extension.

The browser run used a copy of the genuine model-task ledger from `.runtime/multifile-validation/226fe510-73f6-4516-af2e-ba3354c74443`: a 17-event model task, plus a 69-event history created with actual pause/resume commands and file execution. Both reports pass pagination, task isolation, actual server disconnect with retained records, server restart without duplicates, credential isolation, and genuine evidence disclosure. They report no mocks, no simulation, no console errors, and no new model calls or executions during observation. The additional file/control history was prepared before the read-only browser checks.

These captures validate browser presentation and incremental reading of actual recorded history. They do not establish fresh browser-generated model plans, physical robot execution, or robot goal completion. Runtime evidence is local; the portable validation summary is `docs/validation/event-browser-live.json`.

No new raster asset ships with this surface; screenshots are validation evidence. No global design rules, new visual identity, or unrelated incumbent typography are canonized by this narrow record.
