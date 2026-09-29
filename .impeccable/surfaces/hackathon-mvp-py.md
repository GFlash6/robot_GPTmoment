---
version: 1
slug: "hackathon-mvp-py"
primary_target: "hackathon_mvp.py"
related_targets: ["fieldmind.py", "HACKATHON.md", "README.md", ".impeccable/review/desktop.png", ".impeccable/review/mobile.png"]
---

# FieldMind hackathon inspection runtime

Mode: Operate. Audience: hackathon judges, local robotics developers, and on-site operators. Present one real inspection loop clearly enough to demo in three minutes without collapsing weaker model evidence into a stronger robot-completion claim.

## Direction contract

THESIS: A portable Physical Agent Runtime lets a robot see locally, act through constrained skills, and return evidence that an independent verifier can audit.

OWN-WORLD: The Edge Evidence Bay — a near-black, green-cast instrument chassis with scarce phosphor signals, compact telemetry, a dominant raw-evidence viewport, and an explicit four-stage execution chain.

STORY: Confirm the edge host and runtime → state a natural-language inspection goal → optionally name a destination → upload the robot's current frame → execute the local loop → inspect each skill result → read the verifier verdict and raw record.

FIRST VIEWPORT: Keep the FieldMind identity, local/remote runtime status, portable deployment promise, five telemetry cells, and the top of the mission/evidence/execution workbench visible on desktop. The center evidence track is widest. On mobile, show the promise and telemetry first, then preserve mission → evidence → execution order.

FORM: One explicit mission submission. Image evidence is mandatory; destination is optional and means “inspect current position” when empty. Presets only fill the mission text. Running is never implicit, never retried automatically, and never represented as complete before the verifier returns.

DEPLOYMENT: DGX Spark is the high-performance reference deployment used to demonstrate the local inference ceiling. It is not a prerequisite, brand lock-in, or UI assumption; GPU workstations and other edge nodes remain first-class runtime hosts.

EVIDENCE: Preserve the original uploaded frame, surface the four skill states independently, keep the verifier separate from the model assessment, and expose the raw execution record. Empty, waiting, offline, failed, skipped, remote-endpoint, and robot-not-configured states remain explicit.

FINISH: The desktop and mobile captures are the visual truth for this shipped surface. A finish pass must compare both device classes, confirm text-plus-color state communication, and verify that no demo-only data is presented as observed runtime evidence.

## Implemented surface

The surface is a self-contained local web runtime embedded in `hackathon_mvp.py`. Its top bar pairs the offset-square FieldMind mark with a text-labeled runtime indicator. The opening promise uses a large Chinese display line with green emphasis and a compact deployment paragraph that names DGX Spark, GPU workstations, and other edge nodes as portable targets.

Five telemetry cells report accelerator identity, GPU load, memory, model, and robot state. They join directly to the three-column workbench: mission input on the left, raw on-site evidence in the dominant center, and the four-step execution chain plus verifier outcome on the right. The workbench is one bordered chassis rather than a set of floating cards.

The mission form contains a natural-language goal, three quick-fill inspection templates, an optional destination, a mandatory image upload target, and one green execution action. The evidence frame begins empty, then contains the uploaded image without cropping and adds a local-evidence overlay. Processing introduces a single vertical scan line; `prefers-reduced-motion` removes it.

Execution rows keep `robot.navigate`, `vision.observe`, `inspection.assess`, and `task.verify` legible as separate claims. Their waiting, submitted, completed, failed, and skipped states stay independently labeled. The verifier does not simply repeat the model response: only a successful verification output can populate the final verdict and confidence track. The complete response remains inspectable in a native disclosure.

At widths below 1050px the result column spans a second row and the execution trace turns horizontal. Below 720px the shell becomes a single vertical flow, telemetry becomes a two-column grid, a four-part proof strip appears, the evidence viewport contracts to 330px, and the brand descriptor is hidden while FieldMind and runtime status remain visible.

## Completion evidence

This documentation pass inspected the implemented HTML/CSS/JavaScript in `hackathon_mvp.py`, the product and hackathon narratives, and the current desktop and mobile review captures. It records the shipped visual world without changing runtime behavior or asserting additional execution validation.
