---
name: "FieldMind"
description: "A local-first, portable, evidence-driven Physical Agent Runtime for robots."
colors:
  phosphor-green: "#76b900"
  evidence-green: "#b7e36f"
  canvas-black: "#080a08"
  panel-black: "#101411"
  ink-white: "#f4f7f2"
  muted-sage: "#a9b4ac"
  dim-sage: "#909d93"
  structural-line: "#283129"
  failure-coral: "#ff746c"
  caution-amber: "#e5b75e"
typography:
  display:
    fontFamily: "Aptos, Noto Sans SC, sans-serif"
    fontSize: "clamp(36px, 5vw, 74px)"
    fontWeight: 800
    lineHeight: 0.96
    letterSpacing: "-0.04em"
  headline:
    fontFamily: "Aptos, Noto Sans SC, sans-serif"
    fontSize: "24px"
    fontWeight: 800
    lineHeight: 1.1
    letterSpacing: "-0.025em"
  title:
    fontFamily: "Aptos, Noto Sans SC, sans-serif"
    fontSize: "15px"
    fontWeight: 800
    lineHeight: 1.2
    letterSpacing: "-0.01em"
  body:
    fontFamily: "Aptos, Noto Sans SC, sans-serif"
    fontSize: "13px"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: "Aptos, Noto Sans SC, sans-serif"
    fontSize: "11px"
    fontWeight: 500
    lineHeight: 1.2
    letterSpacing: "0.12em"
  mono:
    fontFamily: "ui-monospace, monospace"
    fontSize: "11px"
    fontWeight: 400
    lineHeight: 1.55
rounded:
  field: "10px"
  dropzone: "12px"
  shell: "14px"
  pill: "999px"
  circle: "50%"
spacing:
  xs: "7px"
  sm: "10px"
  md: "14px"
  lg: "18px"
  xl: "24px"
  shell: "28px"
components:
  button-primary:
    backgroundColor: "{colors.phosphor-green}"
    textColor: "{colors.canvas-black}"
    rounded: "{rounded.field}"
    padding: "13px 16px"
  button-primary-hover:
    backgroundColor: "#86c91c"
    textColor: "{colors.canvas-black}"
    rounded: "{rounded.field}"
    padding: "13px 16px"
  chip-preset:
    backgroundColor: "transparent"
    textColor: "{colors.muted-sage}"
    rounded: "{rounded.pill}"
    padding: "7px 10px"
  input-dark:
    backgroundColor: "#0a0d0a"
    textColor: "{colors.ink-white}"
    rounded: "{rounded.field}"
    padding: "12px 13px"
  container-workbench:
    backgroundColor: "{colors.panel-black}"
    textColor: "{colors.ink-white}"
    rounded: "{rounded.shell}"
    padding: "24px"
---

# Design System: FieldMind

## Overview

**Creative North Star: "The Edge Evidence Bay"**

FieldMind should feel like a disciplined workstation installed beside the robot, not a cloud dashboard wearing industrial colors. Its near-black canvas, instrument-like telemetry, and sharp evidence viewport create a calm operating bay where the user can issue one mission, inspect what the robot actually saw, and follow the chain from skill invocation to independent verification.

The visual system communicates three durable product truths: computation can stay local, the runtime can move between edge hosts, and claims only become conclusions when evidence survives verification. DGX Spark belongs in deployment copy as a high-performance reference node; it is never treated as a required device or the identity of the product. Density is purposeful rather than decorative: large type states the promise, compact labels expose machine state, and green appears only where it carries action, availability, progress, or verified success.

**Key Characteristics:**

- Near-black, green-cast instrument surfaces with thin structural dividers.
- One luminous green signal family reserved for action, live state, evidence framing, and success.
- Oversized bilingual-capable display type paired with compact telemetry labels and monospaced raw evidence.
- A visible left-to-right operating model: mission input, on-site evidence, then execution and verifier outcome.
- Honest empty, offline, waiting, failed, skipped, and unknown states; no simulated success content.

## Colors

The palette is an edge-compute night mode: green-black surfaces reduce glare, cool sage neutrals hold dense operational copy, and the phosphor accent behaves like a scarce status lamp.

### Primary

- **Phosphor Action Green** (`phosphor-green`, #76b900): primary actions, live runtime dots, completed step indices, progress fills, and the brand mark.
- **Evidence Signal Green** (`evidence-green`, #b7e36f): emphasized promise text, focus outlines, evidence framing, scan lines, and local-frame metadata.

### Secondary

- **Caution Amber** (`caution-amber`, #e5b75e): skipped or limited states and remote/non-local runtime warnings.
- **Failure Coral** (`failure-coral`, #ff746c): failed execution steps and offline/error status. It communicates failure without competing with the primary action.

### Neutral

- **Canvas Black** (`canvas-black`, #080a08): application background and the deepest evidence overlays.
- **Panel Black** (`panel-black`, #101411): telemetry and workbench surfaces.
- **Ink White** (`ink-white`, #f4f7f2): primary headings, values, and task-defining content.
- **Muted Sage** (`muted-sage`, #a9b4ac): explanatory copy, field labels, and secondary control text.
- **Dim Sage** (`dim-sage`, #909d93): metadata, timestamps, placeholders, and waiting states.
- **Structural Line** (`structural-line`, #283129): shared borders and dividers that make the information architecture visible without creating bright boxes.

### Named Rules

**The Evidence Signal Rule.** Green must mean action, live capability, scanning, or verified progress; it is not ambient decoration.

**The Honest State Rule.** Failure uses coral, constrained or skipped states use amber, and unknown or waiting states remain neutral. Never turn every state green.

**The Portable Runtime Rule.** Host and accelerator identity may be visible telemetry, but no vendor color or device name may overtake FieldMind's product identity.

## Typography

**Display Font:** Aptos (with Noto Sans SC and system sans-serif fallbacks)  
**Body Font:** Aptos (with Noto Sans SC and system sans-serif fallbacks)  
**Label/Mono Font:** UI monospace (with generic monospace fallback)

**Character:** The sans-serif system is direct, engineered, and highly legible in mixed Chinese and English. Tight display tracking creates confidence; small uppercase labels and tabular values evoke instrumentation; monospaced text is reserved for evidence and protocol output.

### Hierarchy

- **Display** (800, fluid 36–74px, 0.96 line-height): the single product promise in the introductory band; highlighted words may use Evidence Signal Green.
- **Headline** (800, 24px, 1.1 line-height): verifier outcomes and other decisive result statements.
- **Title** (800, 15px, 1.2 line-height): workbench section names and compact operational headings.
- **Body** (400, 13px, 1.5 line-height): instructions, explanations, verdict summaries, and form content; longer introductory prose opens to 1.6 line-height.
- **Label** (500, 11px, 0.12em tracking, uppercase for machine labels): telemetry keys, proof labels, and compact state metadata.
- **Mono** (400, 11px, 1.55 line-height): raw execution records, frame metadata, and numbered skill markers.

### Named Rules

**The Two Voices Rule.** Human intent and conclusions use the sans-serif voice; raw evidence, indices, timings, and protocol output use mono.

**The One Promise Rule.** Reserve the oversized display treatment for one product-level statement per surface; operational content stays compact and scannable.

## Layout

The desktop shell is centered with a 1500px maximum width and 28px outer padding. A 72px top bar establishes identity and runtime state, followed by a wide promise band, a shared telemetry rail, and a single bordered workbench. The primary desktop workbench uses three unequal tracks: a compact mission column, a dominant evidence column, and a result column. Column dividers align with the telemetry structure above so the interface reads as one instrument rather than a collection of cards.

At 1050px and below, the first two columns remain side by side while execution and verification span the next row; the four execution steps become a horizontal trace. At 720px and below, the shell padding contracts to 16px, the product descriptor is hidden, telemetry becomes a two-column grid, and all workbench regions stack in mission → evidence → execution order. A four-cell proof strip appears between telemetry and the workbench to keep local model, skills, raw evidence, and independent verification visible before scrolling into the workflow.

Spacing follows compact operational increments from 7px to 28px. Internal workbench padding is 24px on desktop and 20px on mobile. Avoid free-floating cards and arbitrary gutters; use shared borders, aligned rails, and contiguous surfaces to express system relationships.

**The Evidence-First Width Rule.** When horizontal space is available, the on-site evidence viewport receives the widest track. The composition may stack, but evidence must not be reduced to a thumbnail beside secondary metadata.

**The Workflow Order Rule.** Responsive reflow preserves mission input, raw evidence, execution chain, then verifier verdict. Never move the conclusion ahead of the evidence that supports it.

## Elevation & Depth

FieldMind is flat by default. Depth comes from nested green-black tones, 1px borders, and contained clipping rather than a stack of floating cards. The primary action is the lone raised control, while live status uses a small optical glow. Evidence overlays use a nearly opaque dark backing so machine metadata remains legible over imagery.

### Shadow Vocabulary

- **Action Lift** (`0 7px 22px rgba(47, 76, 11, 0.32)`): only the enabled primary execution button.
- **Runtime Glow** (`0 0 12px rgba(118, 185, 0, 0.55)`): the live runtime dot; never apply this glow to decorative text or entire panels.
- **Brand Offset** (`7px 7px 0 #395b18`): the square FieldMind mark's physical offset; it is a signature silhouette, not a general card shadow.

### Named Rules

**The Flat Bay Rule.** Surfaces remain flat and joined at rest; only action, live status, and the brand mark may cast a shadow.

## Shapes

The form language combines a strict equipment chassis with forgiving controls. The telemetry-and-workbench assembly forms one 14px outer shell, while inputs and the primary button use 10px corners and the upload target uses 12px corners. Preset chips are fully pill-shaped, and skill indices and runtime indicators are circular. The evidence viewport stays rectangular and uses cropped corner brackets instead of a rounded-card silhouette.

Thin borders are structural, not ornamental. Dashed borders are reserved for file acquisition; solid borders define fields, panels, evidence frames, and separators. The offset double-square brand mark and paired evidence brackets are the two recurring geometric signatures.

**The Chassis-and-Controls Rule.** Round the outer chassis and touch targets; keep the visual evidence plane rectilinear and instrument-like.

## Components

### Buttons

- **Shape:** compact, gently curved rectangle (10px radius) with a full-width execution variant.
- **Primary:** Phosphor Action Green with Canvas Black text and 13px × 16px padding; use strong weight for the one action that initiates real work.
- **Hover / Focus:** hover brightens to the established active green; keyboard focus uses a 2px Evidence Signal Green outline with a 3px offset.
- **Disabled:** muted green-black fill, low-contrast sage text, wait cursor, and no lift; the label must still explain the pending action.

### Chips

- **Style:** transparent fill, Structural Line border, Muted Sage text, pill silhouette, and compact 7px × 10px padding.
- **State:** these are quick mission templates, not filters. Hover increases border and text contrast; activation populates the mission field without implying execution.

### Cards / Containers

- **Corner Style:** joined shell corners (14px) for the telemetry/workbench assembly; internal columns do not become independent cards.
- **Background:** Panel Black over Canvas Black, with deeper black reserved for fields and the evidence viewport.
- **Shadow Strategy:** flat by default; see the Flat Bay Rule.
- **Border:** 1px Structural Line dividers align across regions.
- **Internal Padding:** 24px for workbench columns, reduced to 20px on mobile.

### Inputs / Fields

- **Style:** deep green-black field, thin muted structural stroke, 10px radius, and 12px × 13px padding.
- **Focus:** explicit Evidence Signal Green outline with a 3px offset; upload targets also shift their dashed border to Phosphor Action Green.
- **Error / Disabled:** errors are stated beside the verifier/result region and use Failure Coral for status affordances; placeholders and unavailable values stay Dim Sage rather than disappearing.

### Navigation

The product bar is a minimal identity-and-status rail rather than global navigation: FieldMind and its Physical Agent descriptor sit left, and runtime state sits right. On mobile, hide the descriptor but retain both the brand and runtime state. The live dot never appears without adjacent text.

### Evidence Viewport

The evidence viewport is the dominant signature component: a near-black rectangular frame with two thin green corner brackets, a centered honest empty state, a contained full-frame image, and a monospaced local-evidence overlay. During processing, one thin scan line travels vertically with a restrained easing curve; reduced-motion preferences remove it entirely.

### Execution Trace and Verifier

Four numbered steps expose navigation, observation, model assessment, and independent verification as separate states. Completed indices fill green; failed indices turn coral; skipped indices turn amber; waiting remains neutral. The verifier follows the chain with a decisive headline, supporting explanation, confidence value and a 3px progress track. Raw execution JSON remains available in a disclosure beneath the verdict.

## Do's and Don'ts

### Do:

- **Do** make raw on-site evidence and the independent verifier visually distinct from model interpretation.
- **Do** keep runtime, accelerator, model, and robot connection telemetry explicit and truthful.
- **Do** treat DGX Spark as a named high-performance reference deployment while preserving GPU-workstation and other edge-node portability in copy.
- **Do** preserve visible focus, text labels beside status colors, and reduced-motion behavior.
- **Do** maintain the desktop-to-mobile workflow order and the contiguous chassis structure.

### Don't:

- **Don't** imply that an HTTP response, model answer, confidence score, or green state alone proves robot task completion.
- **Don't** turn the palette into generic neon cyberpunk; green is a scarce operational signal against restrained green-black surfaces.
- **Don't** add floating glass cards, gradient washes, decorative charts, or unrelated imagery that compete with the on-site frame.
- **Don't** hard-bind the visual identity or product promise to DGX Spark, a single GPU model, or a single robot adapter.
- **Don't** fabricate populated evidence, success states, or telemetry to make an empty runtime look complete.
