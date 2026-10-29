# Decisions and lessons

Why Crosscut is built the way it is, what didn't work, and what is still unconfirmed.
Newest entries first within each section. Keep each entry short.

## Requirements from the maintainer

What was actually asked for or explicitly discussed (2026-10-22 unless dated). Everything not on
this list is an assumption, tracked in the table at the end.

| ID | Requirement | Status in 0.1.0 |
| --- | --- | --- |
| R-010 | Test the add-on in Blender, fix all the bugs, provide an installable zip (2026-10-29) | 0.2.0: in-Blender test suite, fixes below, `dist/crosscut-0.2.0.zip` |
| R-009 | First user test: "looks great but definitely buggy"; next build should be run and tested in Blender before he gives detailed feedback (2026-10-26) | Done in 0.2.0; awaiting his test |
| R-008 | Name: maintainer created the repo as `blender-crosscut`, accepting "Crosscut" (2026-10-26) | Done |
| R-007 | Search for existing solutions before building | Done: none did live Solid-mode capping on top of Alt+B (Bonsai cutaway, Section Toolbox, Section Box, RadCut, Clip View and others reviewed) |
| R-006 | Standalone add-on first; weigh whether it belongs in Bucket Builder; later compare the experience tied to bucket dimensions | Standalone; generic range object (D-001, D-007) |
| R-005 | Netfabb-style slider to scrub the plane across the parts / build volume | Scrub slider, step buttons, Shift+Alt+Wheel |
| R-004 | Show only a slice (cross-section) instead of a half cut, replacing the thin-box boolean intersect workaround | Slice mode: thickness 0 = section only, > 0 = slab |
| R-003 | Decide how overlapping solid bodies display (comparing sections of several parts is common) | Per-object hatch variation + interference highlight (D-004) |
| R-002 | Toggle easily between seeing backfaces (native Alt+B) and a solid cross-section look as in CAD section views; reference mock-ups in `docs/images/reference/` | Cap styles Backfaces / Solid / Hatched |
| R-001 | Main use: while modelling parts. Secondary: finding interferences when packing buckets | Drives defaults |

## Decisions

### Bugs found in the first in-Blender run (0.2.0, 2026-10-29)

What `tests/blender/run_viewport_tests.py` and the screenshots showed in 0.1.0, and the fix:

- **No clipping unless Alt+B had been used in that view.** Blender only clips a view that has a
  clipping box (`rv3d->clipbb`), which only `view3d.clip_border` creates. Crosscut drew outlines on
  an uncut part. Fix: D-008.
- **Washed-out colours, grey hatch lines.** The POST_VIEW buffer is linear (D-009); 0.1.0
  converted colours to sRGB first, so they were brightened twice.
- **Section often looked like nothing happened**: it always kept the side opposite the normal,
  which is often the side facing the camera. Fix: D-010.
- **White default objects got white caps** that read as uncut. Fix: D-011.
- **Open (non-manifold) sections filled with even-odd garbage triangles.** Fix: D-012.
- **Readout showed `1.2 cm` in a mm scene** (`units.to_string` picks its own unit) and `[Hatch]`
  instead of the UI's "Hatched". Now uses Scene > Units > Length and the enum names. The Targets &
  Range panel shows units too.
- **One-frame lag** on every change: planes were only written in the draw callback, after the
  scene was drawn. Now pushed from property updates, operators and the depsgraph handler.
- **Hatch antialiasing** was wider than the line itself, so lines never reached their colour.
- UI: Off showed an open-eye icon; Flip sat next to Step and stayed active in Slice mode (now at
  the end of the axis row, Section only); hatch spacing had no unit (now "Spacing (px)"); hatch
  spacing and outline width now follow the UI scale.
- Checked and fine in 4.2.23 and 5.2.3 (5.2 also on Vulkan): even-odd mask with INVERT blend,
  interference pass, depth-tested caps, Alt+B hand-off and restore, quad view, Edit Mode edits,
  modifiers, collection instances, Selected targets, Wireframe/X-ray, scrub get/set, every
  operator, pie and popover. No difference between 4.2 and 5.2 found.

### D-012: Close open contours before filling (2026-10-29)

- **Context:** Real meshes are often slightly non-manifold; an open contour makes the even-odd
  fan fill nonsense.
- **Decision:** Pair open endpoints nearest-first with extra segments before building the mask.
  The orange outline and "Open section" warning stay, so the user still learns the mesh is open.
- **Revisit if:** big holes give misleading fills; then skip the fill above some gap size.

### D-011: Auto colours: white or grey parts get the Cap Color (2026-10-29)

- **Context:** Blender's default object colour is white and default material grey, so Auto
  (follow the shading colour) gave white caps that read as uncut. The reference mock-up uses a
  green cap on a grey part.
- **Decision:** In Auto, an unsaturated object/material colour uses the Cap Color (default green);
  coloured parts keep their colour. Object / Material / Single / Palette are unchanged.

### D-010: A new section keeps the far side (2026-10-29)

- **Context:** A fixed kept side meant half the time the camera saw the intact outside.
- **Decision:** The Section X/Y/Z operators (pie, panel) and the on/off toggle set Flip so the side
  facing the viewer is cut away. Changing the mode or axis in the panel enum does not flip (no
  view there). Supersedes Q-004 for the operators.

### D-009: Colours sent to shaders are linear (2026-10-29)

- **Context:** Measured in 4.2 and 5.2: a fill of sRGB-intended 0.85 displayed as 237, i.e. the
  POST_VIEW overlay buffer is scene-linear and gets the display transform afterwards.
- **Decision:** All shader colours are linear. Object and material colours are used as stored;
  the Cap Color (COLOR_GAMMA), the palette and constants go through `_lin()`.

### D-008: Create the view's clipping box with an empty Alt+B (2026-10-29)

- **Context:** `RegionView3D.clip_planes` and `use_clip_planes` do nothing without
  `rv3d->clipbb`, which RNA cannot create. clip_border also draws a faint tint over its box.
- **Decision:** When Crosscut takes over a view that has no clipping on, it runs
  `view3d.clip_border` once with an empty rectangle (0,0,0,0) under a context override: this
  creates a degenerate box (no visible tint), then Crosscut writes its own planes. From property
  updates it runs right away; from the draw callback it is deferred to a timer.
- **Alternatives considered:** a 1-pixel or off-screen box (works, but leaves a thin tinted sliver
  that shows when orbiting); requiring the user to press Alt+B first (bad UX).
- **Revisit if:** Blender exposes the clipping box in RNA, or clip_border changes behaviour.

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
- **Revisit if:** Material Preview support becomes a must.
- **Update 2026-10-29:** the "revisit if" fired: with no Alt+B box there was no clipping at all
  (D-008), and planes written in the draw callback lagged a frame. Planes are now pushed from
  property updates, operators and the depsgraph handler; the draw callback is a fallback.

### D-001: Standalone add-on, not part of Bucket Builder (2026-10-22)

- **Context:** Sectioning is useful for any modelling; the core has nothing MJF-specific.
- **Decision:** Separate add-on. Bucket-specific value comes through generic settings (range
  object, step, interference).
- **Revisit if:** bucket integration needs more than Bucket Builder setting Crosscut's scene settings.

## Tried and abandoned

### T-002: A tiny or off-screen Alt+B box to get a clipping box (2026-10-29)

- **What we tried:** `view3d.clip_border` over a 1-pixel rectangle at a corner, or off-screen.
- **Why we dropped it:** it works, but Blender tints its clipping box, which then shows as a thin
  sliver when orbiting. An empty rectangle gives a degenerate box with no tint (D-008).
- **Worth retrying if:** the empty rectangle stops working in a future Blender.

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
| Q-004 | Section keeps the side opposite the plane normal (a Z section keeps everything below) | assumption | 0.1.0 | replaced by D-010 for the operators |
| Q-005 | Slice slabs are centred on the plane | assumption | 0.1.0 | open |
| Q-006 | Default step 0.08 (one MJF layer) | assumption | 0.1.0 | open |
| Q-007 | Targets default to all visible solids; Wire/Bounds-display objects, the plane object and the range object are never capped | assumption | 0.1.0 | open |
| Q-008 | Cap colour follows the Solid shading colour type (Object / Material), else a per-object palette. The reference mock-up used a green cap on a grey part | assumption | 0.1.0 | refined by D-011 |
| Q-009 | Hotkeys: Shift+Alt+B pie, Shift+Alt+Wheel step (Ctrl x10); header toggle + popover | assumption | 0.1.0 | open |
| Q-010 | Caps only in Solid/Wireframe (Blender doesn't clip Material Preview / Rendered) | assumption | 0.1.0 | open |
| Q-011 | License GPL-3.0-or-later (matches the LICENSE the maintainer added) | assumption | 0.1.0 | confirmed by repo |
| Q-012 | Which Blender version is in daily use | unasked question | 0.1.0 | open |
| Q-013 | Whether to override Alt+B itself rather than add new hotkeys | unasked question | 0.1.0 | open |
| Q-014 | Screen-space vs. model-space hatching as default | unasked question | 0.1.0 | open |
| Q-015 | Whether Material Preview support matters | unasked question | 0.1.0 | open |
| Q-016 | Whether a 6-plane section box is wanted | unasked question | 0.1.0 | open |
| Q-017 | Bugs from the maintainer's first test (details pending; first do our own Blender test pass) | follow-up | R-009 | own pass done in 0.2.0; his details still welcome |
| Q-018 | Bucket Builder integration: auto-pick the bucket as range, printer layer index, interference list | follow-up | R-006 | open |
| Q-019 | Section box (up to 6 planes) and multiple independent planes | follow-up | 0.1.0 | open |
| Q-020 | Export the section (curve / mesh / SVG); section and interference area readouts | follow-up | 0.1.0 | open |
| Q-021 | Per-object cap colour override, cap opacity | follow-up | 0.1.0 | open |
| Q-022 | Large scenes: spatial index so scrubbing only touches crossing triangles | follow-up | 0.1.0 | open |
| Q-023 | After hand-back, Blender may keep tinting an old Alt+B box | follow-up | 0.1.0 | open |
| Q-024 | Headless CI for the pure-numpy tests (GitHub Actions) | follow-up | 0.1.0 | open |
| Q-025 | Create GitHub Issues for the roadmap | follow-up | ai-context conventions | done 2026-10-29 (opened directly, per the 2026-10-26 convention) |
| Q-026 | Section keeps the far side when switched on from the operators (D-010) | assumption | 0.2.0 | open |
| Q-027 | Auto colours: white/grey parts get the green Cap Color (D-011) | assumption | 0.2.0 | open |
| Q-028 | Open contours are closed nearest-first and filled, still flagged orange (D-012) | assumption | 0.2.0 | open |
| Q-029 | Default hatch spacing 10 px looks denser than the mock-up on a large screen | unasked question | 0.2.0 | open |
