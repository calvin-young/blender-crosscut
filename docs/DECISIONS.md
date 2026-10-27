# Decisions and lessons

Why Crosscut is built the way it is, what didn't work, and what is still unconfirmed.
Newest entries first within each section. Keep each entry short.

## Requirements from the maintainer

What was actually asked for or explicitly discussed (2026-10-22 unless dated). Everything not on
this list is an assumption, tracked in the table at the end.

| ID | Requirement | Status in 0.1.0 |
| --- | --- | --- |
| R-009 | First user test: "looks great but definitely buggy"; next build should be run and tested in Blender before he gives detailed feedback (2026-10-26) | Open |
| R-008 | Name: maintainer created the repo as `blender-crosscut`, accepting "Crosscut" (2026-10-26) | Done |
| R-007 | Search for existing solutions before building | Done: none did live Solid-mode capping on top of Alt+B (Bonsai cutaway, Section Toolbox, Section Box, RadCut, Clip View and others reviewed) |
| R-006 | Standalone add-on first; weigh whether it belongs in Bucket Builder; later compare the experience tied to bucket dimensions | Standalone; generic range object (D-001, D-007) |
| R-005 | Netfabb-style slider to scrub the plane across the parts / build volume | Scrub slider, step buttons, Shift+Alt+Wheel |
| R-004 | Show only a slice (cross-section) instead of a half cut, replacing the thin-box boolean intersect workaround | Slice mode: thickness 0 = section only, > 0 = slab |
| R-003 | Decide how overlapping solid bodies display (comparing sections of several parts is common) | Per-object hatch variation + interference highlight (D-004) |
| R-002 | Toggle easily between seeing backfaces (native Alt+B) and a solid cross-section look as in CAD section views; reference mock-ups in `docs/images/reference/` | Cap styles Backfaces / Solid / Hatched |
| R-001 | Main use: while modelling parts. Secondary: finding interferences when packing buckets | Drives defaults |

## Decisions

### D-007: Generic scrub-range object instead of Bucket Builder coupling (2026-10-22)

- **Context:** Scrubbing across a build volume is the main bucket use case.
- **Decision:** Any object can be the scrub range (its bounds); it is excluded from capping. The
  readout shows `step k / n` with the step size, which reads as a layer index.
- **Alternatives considered:** reading Bucket Builder's bucket directly (couples the add-ons).
- **Revisit if:** the maintainer wants auto-detection of the bucket, layer numbering that matches
  the printer, or interference reports.

### D-006: Pressing Alt+B while Crosscut is active hands clipping back to Blender (2026-10-22)

- **Context:** Both Blender and Crosscut write the same `clip_planes`.
- **Decision:** Crosscut remembers what it wrote; if the planes change under it (Alt+B toggles off
  or draws a new box) it switches itself off and leaves Blender's state alone. When Crosscut is
  turned off it restores the clipping that was there before.
- **Revisit if:** testing shows flicker, fights, or lost Alt+B boxes.

### D-005: Caps also on Blender's own Alt+B box (2026-10-22)

- **Decision:** With Crosscut off, a native Alt+B region still gets caps (setting "Cap Alt+B Clipping", on by default).

### D-004: Several bodies: vary hatch per object, highlight interference (2026-10-22)

- **Context:** Comparing sections of several overlapping parts is common.
- **Decision:** Hatch direction, then spacing, alternates per object (ISO 128-50 style). Where two
  or more objects' sections overlap, the overlap is cross-hatched in red.
- **Alternatives considered:** same hatch for all (last-drawn wins, overlap hidden); solid fill with
  interference; backface tint (overlap invisible). See `docs/images/concepts/multibody.png`.
- **Revisit if:** the maintainer prefers another look after using it.

### D-003: Even-odd fan mask instead of triangulating section contours (2026-10-22)

- **Context:** Section contours of real meshes have holes, islands and the odd defect; chaining
  and triangulating them on the CPU is fragile.
- **Decision:** Each section segment becomes a fan triangle from a shared apex, rasterized with
  invert blending into an offscreen mask; a pixel is lit when covered an odd number of times
  (inside the section). A quad on the plane then paints lit pixels with the scene depth test.
- **Alternatives considered:** CPU contour triangulation (real cap mesh, exportable, but fragile
  and slower to scrub); stencil buffer (not exposed in Blender's Python `gpu` module).
- **Revisit if:** caps must be exported or rendered, or the invert blend proves unreliable on a
  GPU backend.

### D-002: Build on viewport clip planes plus GPU caps (2026-10-22)

- **Context:** Needs to be live, non-destructive, and work in Solid mode where modelling happens.
- **Decision:** Write the plane(s) into `RegionView3D.clip_planes` (what Alt+B sets) so Blender
  clips drawing and selection itself; Crosscut only draws caps, outlines and a readout. The section
  is computed in numpy and cached per object and plane.
- **Alternatives considered:** backface-tint material override (Material Preview only, relies on
  normals, can't show overlap or slices); live boolean/bisect modifiers (slow, changes the stack).
- **Revisit if:** writing clip planes from the draw callback misbehaves (one-frame lag, redraw
  loops, crashes when no Alt+B box was ever drawn), or Material Preview support becomes a must.

### D-001: Standalone add-on, not part of Bucket Builder (2026-10-22)

- **Context:** Sectioning is useful for any modelling; the core has nothing MJF-specific.
- **Decision:** Separate add-on. Bucket-specific value comes through generic settings (range
  object, step, interference).
- **Revisit if:** bucket integration needs more than Bucket Builder setting Crosscut's scene settings.

## Tried and abandoned

### T-001: Testing 0.1.0 in the cloud sandbox where it was written (2026-10-22)

- **What we tried:** run Blender in the development sandbox to verify drawing and capture real
  screenshots.
- **Why it didn't work:** Blender couldn't be downloaded there, so 0.1.0 shipped with only the
  numpy math and the clip-plane state machine tested (stubs), plus concept renders. The first real
  run was the maintainer's.
- **Worth retrying if:** n/a. Development moved to a dedicated machine with Blender (2026-10-26).

## Open questions and assumptions

| ID | Item | Type | From | Status |
| --- | --- | --- | --- | --- |
| Q-001 | Blender 4.2+ extension format only (no legacy `bl_info`) | assumption | 0.1.0 | open |
| Q-002 | Settings live on the Scene and save with the .blend | assumption | 0.1.0 | open |
| Q-003 | Default cap style Hatched, 45 degrees, screen-space spacing 10 px | assumption | 0.1.0 | open |
| Q-004 | Section keeps the side opposite the plane normal (a Z section keeps everything below) | assumption | 0.1.0 | open |
| Q-005 | Slice slabs are centred on the plane | assumption | 0.1.0 | open |
| Q-006 | Default step 0.08 (one MJF layer) | assumption | 0.1.0 | open |
| Q-007 | Targets default to all visible solids; Wire/Bounds-display objects, the plane object and the range object are never capped | assumption | 0.1.0 | open |
| Q-008 | Cap colour follows the Solid shading colour type (Object / Material), else a per-object palette. The reference mock-up used a green cap on a grey part | assumption | 0.1.0 | open |
| Q-009 | Hotkeys: Shift+Alt+B pie, Shift+Alt+Wheel step (Ctrl x10); header toggle + popover | assumption | 0.1.0 | open |
| Q-010 | Caps only in Solid/Wireframe (Blender doesn't clip Material Preview / Rendered) | assumption | 0.1.0 | open |
| Q-011 | License GPL-3.0-or-later (matches the LICENSE the maintainer added) | assumption | 0.1.0 | confirmed by repo |
| Q-012 | Which Blender version is in daily use | unasked question | 0.1.0 | open |
| Q-013 | Whether to override Alt+B itself rather than add new hotkeys | unasked question | 0.1.0 | open |
| Q-014 | Screen-space vs. model-space hatching as default | unasked question | 0.1.0 | open |
| Q-015 | Whether Material Preview support matters | unasked question | 0.1.0 | open |
| Q-016 | Whether a 6-plane section box is wanted | unasked question | 0.1.0 | open |
| Q-017 | Bugs from the maintainer's first test (details pending; first do our own Blender test pass) | follow-up | R-009 | open |
| Q-018 | Bucket Builder integration: auto-pick the bucket as range, printer layer index, interference list | follow-up | R-006 | open |
| Q-019 | Section box (up to 6 planes) and multiple independent planes | follow-up | 0.1.0 | open |
| Q-020 | Export the section (curve / mesh / SVG); section and interference area readouts | follow-up | 0.1.0 | open |
| Q-021 | Per-object cap colour override, cap opacity | follow-up | 0.1.0 | open |
| Q-022 | Large scenes: spatial index so scrubbing only touches crossing triangles | follow-up | 0.1.0 | open |
| Q-023 | After hand-back, Blender may keep tinting an old Alt+B box | follow-up | 0.1.0 | open |
| Q-024 | Headless CI for the pure-numpy tests (GitHub Actions) | follow-up | 0.1.0 | open |
| Q-025 | Create GitHub Issues for the roadmap (draft, maintainer approves first) | follow-up | ai-context conventions | open |
