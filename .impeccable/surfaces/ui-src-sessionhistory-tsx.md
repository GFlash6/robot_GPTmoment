---
version: 1
slug: "ui-src-sessionhistory-tsx"
primary_target: "ui/src/SessionHistory.tsx"
related_targets: ["ui/src/Workbench.tsx", "ui/src/workbench.css"]
---

# Workbench history summary

Mode: Operate. Audience: local framework developers and robot operators. This brief covers the history-summary controls within the established Workbench. It is a local extension of the existing visual identity.

## Direction contract

THESIS: Let an operator control which conversation originals enter model context, explicitly request a history summary, and inspect its sources without confusing model text with execution evidence.

OWN-WORLD: Inherit the Workbench's muted green accents, light panels, existing typography, native forms, subtle separators and restrained rounded controls.

STORY: Choose automatic summarization policy, set recent-message retention and pinned originals, save the policy, optionally generate a summary, then inspect its points and provenance.

FIRST VIEWPORT: “历史摘要与预算” follows conversation turns inside “目标与上下文”, before reference memory. The existing plan panel remains adjacent on wide screens and stacks below on narrow screens.

FORM: A bounded local addition. Policy saving and saved-summary reading do not call the model. Manual generation is an explicit action; saved automatic policy applies when analysis or planning exceeds its context budget.

## Implemented behavior

The introduction states that original records remain preserved and a summary cannot establish execution success. The automatic-policy checkbox, labeled recent-message number input and native pinned-message disclosure precede the save and generate actions. Recent retention accepts whole numbers from 2 through 32, defaulting to 6 when no stored policy exists. The retained originals are the union of the last N messages and all pinned messages, not a shared N-message allowance. The corrected helper says “可设为 2–32 条，同时保留所有指定消息。超预算且无法缩减时会停止调用。” The pin selector shows message number, operator/goal-analysis role and a 160-character excerpt, and allows up to 64 selections.

Editing policy displays an unsaved status and warns that saving invalidates old goal analysis and plan drafts. The synchronized status states that saving does not call the model. Saving submits the session revision and policy; the Workbench adopts the returned session and clears its displayed draft and explanation. The manual “立即生成历史摘要” action remains disabled while policy edits are unsaved, a saved summary is loading, or no older unpinned message can be summarized. Invalid retention values, disconnection and busy state also prevent the relevant actions. An explicit empty-eligibility message explains that recent and pinned messages retain their original text.

Saved summaries are read through the session service without a model call. Loading, disconnected, absent-summary and read-error states remain visible. A changed summary identity produces a refresh instruction; service-reported invalid summaries, including source corruption, appear as an alert explaining that originals remain available and the summary can be regenerated after inspection. A session change remounts the component to separate local selections and summary state.

The summary heading identifies model authorship. Its coverage text counts older messages and states that uncovered messages still enter context as originals. Each ordered point has a native disclosure containing source turn IDs and full source text; missing originals request a refresh. A separate raw-record disclosure exposes summary version, coverage and model records. These are provenance inspection controls, not an assertion that a model summary is correct or that a robot task succeeded.

## Established presentation and accessibility

The section uses an inherited top border, 24px vertical margins and 20px top padding. Its heading is 16px, the summary subheading 14px, and notes and disclosure labels 12px in dark green (#40594d). It inherits white form controls, green button borders, 6px corners and 40px minimum button height. No new visual system or shipping raster asset is introduced.

Checkboxes are 18px within labeled rows at least 44px high. The recent-message input has an associated label and helper, with a 100px maximum width. Policy and loading feedback use status semantics; summary errors use an alert. Native checkboxes, numeric input and disclosures preserve their native keyboard behavior. The pin list scrolls above 300px; disclosed source text preserves whitespace and scrolls above 240px. Long text wraps, and actions wrap within the panel. The inherited two-column layout stacks at 1000px and below; panel padding reduces to 16px at 700px and below.

## Completion evidence and limits

`docs/validation/summary-browser-live.json` records a passed real-browser run without mock or simulation, covering policy save without AI, pinned originals, actual summary and source disclosure, actual planning input/output, worker hash verification, draft invalidation, reload restoration and visible source corruption. It records `qwen3.7-plus`, a succeeded worker execution, matching output/evidence SHA-256 values, no console errors and no mobile overflow. Its regression record reports 29 passing tests and 9 passing subtests. These are recorded implementation results, not new executions by this documentation pass.

The recorded scoped visual review says **ship** for summary controls, provenance, mobile layout and the corrected recent/pinned union copy. The final recapture reports no model calls. Local validation screenshots are:

- `.runtime/summary-browser-validation/875bdaf1-f93a-44de-983d-f5fd87ff7c2a/desktop-final.png`
- `.runtime/summary-browser-validation/875bdaf1-f93a-44de-983d-f5fd87ff7c2a/mobile-final.png`

These captures are evidence, not shipping assets. This documentation pass inspected the component, Workbench integration, scoped stylesheet and recorded evidence. The brief does not claim approval of unrelated Workbench surfaces or global accessibility conformance; global design documentation is unchanged.
