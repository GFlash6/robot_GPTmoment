---
version: 1
slug: "ui-src-automations-tsx"
primary_target: "ui/src/Automations.tsx"
related_targets: ["ui/src/Workbench.tsx", "ui/src/workbench.css"]
---

# Workbench failure-event diagnostics

Mode: Operate. Audience: local framework developers and robot operators. This brief records a bounded extension of the established Workbench, preserving its muted green accents, light panels, existing typography and native controls. Global design documentation is unchanged.

## Direction contract

THESIS: Let an operator authorize a bounded, robot-scoped diagnostic rule and inspect model explanations of actual failed executions without confusing diagnosis with recovery or execution success.

OWN-WORLD: Inherit the Workbench's restrained rounded controls, green borders, white fields and subtle separators. No new visual identity or shipping imagery is introduced.

STORY: Set the robot scope, cumulative allowance and diagnostic question; create an enabled rule; inspect the selected rule and its newest diagnostic records; pause or explicitly retry when appropriate.

FIRST VIEWPORT: A dedicated panel follows the existing goal/session and plan/execution area. Its creation form sits beside the wider selected-rule and records column on desktop and above that column on mobile.

FORM: Saving a rule does not call a model. An independently running diagnostic worker consumes eligible new failures within the configured permission and budget. Diagnostic explanations do not execute recovery plans or alter task state.

## Implemented behavior and invariants

The creation form requires a nonblank robot scope and question, with an integer cumulative allowance of 1–100, initially 10. The initial robot is `r1`; the default Chinese question asks for actual failure causes, separation of recorded facts from hypotheses, and event/execution citations. Robot scope is limited to 512 characters and question to 16,000. Busy state disables the form. Each enqueue consumes allowance, including failed, canceled and explicitly repeated diagnoses. The helper makes clear that only events after creation are considered.

The native rule selector displays robot, enabled/paused state, used allowance and a shortened identifier. The selected rule shows its question, enabled state and enqueued count. Pause/enable submits the expected rule revision. Paused-period events are not backfilled, and already-sent model requests can still return. Exhausted allowance has its own status message.

Records are ordered newest first and filtered to the selected rule. Text labels distinguish queued, running, completed, failed, canceled and unresolved diagnosis states. Event sequence and task ID accompany each run. A completed diagnosis includes the explanation summary, a native disclosure for the exact recorded error and references, a separate list of uncertainties when present, and the explicit statement “模型解释，不是执行成功证据。” A raw-record disclosure exposes diagnostic provenance and model records. Diagnosis completion must never be relabeled as robot success.

Only failed or unresolved runs offer explicit retry. Retry is disabled while busy, while reads report an error, when the rule is paused, or when allowance is exhausted. The unresolved-state copy explains that the previous request may already have been processed, a retry creates a new request and consumes allowance, and the original record remains unknown. A repeated run exposes its source run ID. No polling loop automatically retries a mutation or model request.

Polling reads `automation.list` and the selected rule's `automation.runs`, scheduling the next refresh 2.5 seconds after each cycle. These are read-only application actions transported through the Workbench action client, not claims that the action endpoint uses HTTP GET. Manual refresh uses the same reads. Loading and read errors are explicit. Failed refresh preserves the last successful records for the same rule; an error suppresses both misleading no-rules and no-runs empty states and disables pause/enable and retry. Changing the selected rule clears prior runs, and filtering prevents another rule's runs appearing under the new selection.

The Workbench mounts this surface only while connected and when the discovered action catalog advertises `automation.create`. Changing the application credential sets connected state false, unmounting diagnostic data and canceling its pending UI updates and polling timer. Reconnection starts a fresh component. The browser credential is an application operation credential, not a model API key; this surface adds no model credential field.

## Established presentation and accessibility

The panel has 24px top margin and 24px internal padding, reduced to 16px padding at 700px and below. The desktop grid uses a minimum 240px creation column and a records column with twice its fractional width, separated by 32px. At 800px and below it stacks into one column with a 24px gap. The rule selector fills its column with no inherited maximum-width restriction. Long code identifiers wrap.

The inherited body is 14px with 1.65 line height; subsection headings are 16px. Controls retain white backgrounds, green accents, 6px corners and existing button styling. Buttons have a 40px minimum height; disclosure summaries have a 44px minimum height. Record rows use top separators and 20px vertical padding. Raw-record text uses the existing dark green (#40594d).

Inputs and selector have explicit labels; the allowance field associates its helper through `aria-describedby`. Loading and exhausted allowance use status semantics, read failures use an alert, and selected-rule state uses polite live feedback. The textarea and selector have visible accent focus outlines. Native form controls and disclosures preserve keyboard interaction; status meaning is expressed in text rather than color alone. This source review does not establish comprehensive accessibility conformance.

## Completion evidence and limits

The scoped reviewer disposition supplied for this handoff is **ship**, covering four resolved findings: desktop/mobile panel padding of 24px/16px, the full-width selector, preservation of the last successful same-rule records with false empty states suppressed after read errors, and the PRODUCT.md capability exception for explicitly configured bounded automation. That exception permits authorized diagnostic worker calls while preserving read-only polling, no task control, and explicit retry of unknown outcomes.

`docs/validation/automation-browser-live.json` records a passed real-browser run without mock or simulation. Its source is `.runtime/automation-browser-validation/54bc974c-11f0-4e05-98f2-2971f44f02fa/report.json`. Recorded checks cover empty state, allowance validation, creation without a model call, an actual failed execution and queue, displayed source-integrity failure, explicit retry, an actual model response with the exact recorded error, pause disabling retry, reload restoration, enable, desktop/mobile captures and read-only polling. The report records no console errors or mobile overflow.

The actual failure was a local `file.ingest` execution producing `FileNotFoundError`; the diagnostic result cites its event and execution records and declares `is_execution_evidence: false`. The recorded model is `qwen3.7-plus`, with one model call in the proof, despite PRODUCT.md describing the earlier `qwen3.8-max` setup. This evidence establishes that particular local diagnostic path, not physical robot recovery, correctness of every model hypothesis, or coverage of every failure mode.

The same directory's `recapture.json` records a passed read-only final capture and an actual server disconnect preserving the last diagnosis, with no console errors or mobile overflow. It also records `screenshots_reused: true`; do not imply that every retained image was freshly generated. Final visual evidence paths are:

- `.runtime/automation-browser-validation/54bc974c-11f0-4e05-98f2-2971f44f02fa/desktop-final.png`
- `.runtime/automation-browser-validation/54bc974c-11f0-4e05-98f2-2971f44f02fa/mobile-final.png`

These are local validation artifacts, not shipping assets. This documentation pass inspected source and recorded JSON evidence; it did not run the browser, invoke application actions or make model calls. The scoped ship disposition does not approve unrelated Workbench surfaces or global design changes.
