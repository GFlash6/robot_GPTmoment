---
version: 1
slug: "ui-src-modeltest-tsx"
primary_target: "ui/src/ModelTest.tsx"
related_targets: ["ui/src/model-test.css", "ui/src/SemanticContextTest.tsx", "ui/src/semantic-context-test.css", "ui/src/semantic-clarification.css"]
---

# Model test extension

Mode: Operate. Audience: local framework developers and operators. Extend the existing model-record surface without changing its visual system.

## Direction contract

THESIS: Ask a real question and inspect the provider's actual answer alongside independently supplied expectations.

OWN-WORLD: Inherit the current muted green, light panels, existing type and native form conventions.

STORY: Enter a question, optionally set an expected answer, manually send, inspect answer and evidence, reopen persistent history.

FIRST VIEWPORT: Test form on the left, answer and request metadata on the right; send immediately below inputs. Stack on narrow screens.

FORM: Local extension; no concept selection or seed applies. One manual request, visible pending state, no automatic retries. Errors and unjudged answers remain explicit.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance

Existing-world exception: no durable DESIGN.md rewrite; no shipping raster added.

## Implemented surface

The model-record page places the real question-and-answer panel above the existing request ledger and response inspector. The topbar reads “账本只读”, identifying the ledger permission while the separate test form permits explicit model calls.

The panel inherits the incumbent muted green palette, light surfaces, typography and native form conventions. Its form and result area use two equal columns with a 28px gap; at widths of 900px or below they stack with 16px panel padding. History rows also stack at that breakpoint. No durable visual-system change or new raster asset is introduced, so this surface brief is the documentation deliverable; DESIGN.md and its sidecar are unchanged.

The labeled question and optional expected-answer fields precede “发送测试”. The helper explains that expected text is compared in full after trimming outer whitespace and is not sent to the model. The form discloses API usage costs. Sending is disabled while pending, without a ready service, or with an empty question; requests never automatically retry.

The answer area preserves response whitespace and wraps long content. It displays call outcome separately from expected-answer matching or unjudged correctness, followed by elapsed time, returned model, HTTP status and response ID. Empty, pending, missing-key, disconnected-service and failure messages remain explicit. Visible focus outlines, associated labels, alert messages and a polite live result region support keyboard and assistive-technology use.

A native disclosure contains persisted test history and an explicit refresh action. Selecting a record restores its question, expected text and result without sending a new request. The surrounding model-record page continues to state that a model answer does not establish robot success.

### Semantic and context chain extension

The model-record page now begins with an Operate-mode workbench for the production semantic → context → planning chain. Its first viewport places the original robot goal and explicit actions on the left, with the validated semantic archive, context fragments, prepared messages, allocation manifest, and validated plan on the right. The composition stacks at narrow widths while keeping all four output tabs visible as a two-column control grid.

Every external model call remains an explicit paid action with no automatic retry. `GoalAnalyzer` writes the validated analysis to the ledger; the browser receives an audit ID but cannot submit replacement semantic JSON. `ContextBuilder` reloads that validated record and the root's registered skill catalog, persists the resulting context preview under its request ID, and displays the exact prepared planning messages without calling the model. `Planner` accepts only that persisted Context Request ID, rebuilds from its frozen catalog and goal, writes a ContextManifest carrying the same ID, then calls the real model and validates its DAG, skill names, and final verifier. Editing the goal or robot ID invalidates every visible downstream artifact.

When analysis produces an optional clarification question, the workbench shows it and accepts a reply as conversation input to a new, separately audited model analysis. Operators may continue through context generation and planning without replying; unresolved information remains in GoalContext. Empty, non-JSON, rejected, and capability-inexpressible responses stay explicit; no example success response or browser-generated semantic result is available. A validated plan is labeled as planning evidence only and is neither submitted nor represented as robot execution.

## Completion evidence

The implementing agent reports the production build, a real question-and-answer call, 33 Python tests plus 9 subtests (1 skipped), and 4 existing browser tests passing. Final browser screenshots include the corrected “账本只读” copy. These are reported implementation checks; this documentation pass independently inspected the final component and stylesheet and made no code changes.
