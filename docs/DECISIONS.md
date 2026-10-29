# Decisions and lessons

Why Crosscut is built the way it is, what didn't work, and what is still unconfirmed.
Newest entries first within each section. Keep each entry short.

## Requirements from the maintainer

What was actually asked for or explicitly discussed (2026-10-22 unless dated). Everything not on
this list is an assumption, tracked in the table at the end.

| ID | Requirement | Status in 0.1.0 |
| --- | --- | --- |
| R-013 | After testing 0.4.0 (2026-10-29): no outline in Wireframe; show the Wire/Bounds note only when such objects exist, and warn in the readout; stripe width and plane colour/opacity settings; Object with no object must not cut, and the only visible object should be picked automatically; Cap Targets and Scrub Range under Settings; parts selectable in a zero-thickness slice; a slab's second plane in another colour or without stacked tint; hide rather than grey out (except Flip); turning off must not bring back the Alt+B box; prep everything for 1.0, release after review | 0.9.0 (1.0 candidate), see below |
| R-012 | After testing 0.3.0 (2026-10-29): stutter fixed. A toggle between blending and striping overlapping colours; hide Cap Color when Auto doesn't use it; bug: switching Section/Slice on over Alt+B left Alt+B's box shading; Center as the middle button; settings for the interference look; maybe rename "Targets & Range"; "just about ready for a 1.0" | 0.4.0, see below |
| R-011 | After testing 0.2.0 (2026-10-29): defaults Hatch Space Model, Spacing 0.5, Scrub 0.5, everything but the main panel collapsed. Bugs: Alt+B outlines run past the box; dragging parts stutters under Alt+B. UI: Section and Slice as two buttons, one or neither on; cap style row right below; drop "Cap Alt+B Clipping" (Backfaces does that); Backfaces + zero-thickness Slice must show something (outline, maybe backface-red fill); bury Step in a collapsed settings panel; replace Offset with a scrub-by-distance toggle there; add a View button for a static plane parallel to the view; blend overlapping colours when interference is off; optional tint/hatch on the plane frame | 0.3.0, see below |
| R-010 | Test the add-on in Blender, fix all the bugs, provide an installable zip (2026-10-29) | 0.2.0: in-Blender test suite, fixes below, `dist/crosscut-0.2.0.zip` |
| R-009 | First user test: "looks great but definitely buggy"; next build should be run and tested in Blender before the maintainer gives detailed feedback (2026-10-26) | Done in 0.2.0; tested, see R-011 |
| R-008 | Name: maintainer created the repo as `blender-crosscut`, accepting "Crosscut" (2026-10-26) | Done |
| R-007 | Search for existing solutions before building | Done: none did live Solid-mode capping on top of Alt+B (Bonsai cutaway, Section Toolbox, Section Box, RadCut, Clip View and others reviewed) |
| R-006 | Standalone add-on first; weigh whether it belongs in Bucket Builder; later compare the experience tied to bucket dimensions | Standalone; generic range object (D-001, D-007) |
| R-005 | Netfabb-style slider to scrub the plane across the parts / build volume | Scrub slider, step buttons, Shift+Alt+Wheel |
| R-004 | Show only a slice (cross-section) instead of a half cut, replacing the thin-box boolean intersect workaround | Slice mode: thickness 0 = section only, > 0 = slab |
| R-003 | Decide how overlapping solid bodies display (comparing sections of several parts is common) | Per-object hatch variation + interference highlight (D-004) |
| R-002 | Toggle easily between seeing backfaces (native Alt+B) and a solid cross-section look as in CAD section views; reference mock-ups in `docs/images/reference/` | Cap styles Backfaces / Solid / Hatched |
| R-001 | Main use: while modelling parts. Secondary: finding interferences when packing buckets | Drives defaults |

## Decisions

### Changes after the maintainer's test of 0.4.0 (0.9.0, 2026-10-29)

- **Turning off leaves no clipping** (D-019). This also explains the "random slicing" with an
  Object plane and no object: with no plane, Crosscut released the view, and releasing put the
  old Alt+B planes back.
- **Object plane**: no object = no cut, with a readout hint. When Object is chosen with none
  set, the only visible Empty is picked, else the only visible object (*assumed* reading of
  "automatically selected as the target": the plane object, not the cap targets). A part used
  as its own plane is still capped; only a flat mesh (a cutter) used as the plane is excluded.
  An Empty plane starts through the Empty (offset 0), anything else in the middle of the range.
- **Selecting in a zero-thickness slice** (D-020).
- **Wireframe**: clipped, but no caps or outlines.
- **Wire/Bounds note**: shown in Cap Targets and in the readout only when such solids are
  visible; the scrub range object is left out (it is uncapped on purpose).
- **Settings**: Stripe Width (px or scene units, following the hatch space); plane Color, Second
  Plane colour (Slice only) and Opacity. A slab draws its nearer plane, then the farther one
  only outside it, so looking through both doesn't double the tint (both requested options,
  done together).
- **UI**: hidden instead of greyed out, except Flip. Scrub and its buttons hide while Crosscut is
  off; hatch settings hide unless Hatched; Interference hides with Backfaces; Cap Targets and
  Scrub Range are sub-panels of Settings.
- **1.0 prep**: README rewritten with fresh screenshots, `docs/USER_GUIDE.md`, `CHANGELOG.md`,
  manifest version 0.9.0 (*assumed*: the candidate is 0.9.0 and the release will be 1.0.0).

### D-020: Click-select by section in a zero-thickness slice (2026-10-29)

- **Context:** Blender doesn't select clipped geometry, and a zero-thickness slice clips
  everything.
- **Decision:** `crosscut.select_section` on the select click (left or right, following the
  keymap preference) in the 3D View keymap. It only runs in a zero-thickness slice: it casts
  the click onto the plane and does an even-odd test against each part's cached section. A hit
  selects (Shift toggles; overlapping parts cycle). A miss passes the click on to Blender.
  Box select still doesn't work there.

### D-019: Releasing a view turns clipping off (2026-10-29)

- **Context:** 0.2.0 to 0.4.0 put back whatever clipping a view had before Crosscut took over
  (D-006). Since 0.4.0 the old Alt+B box's shading can't come back with it, and the maintainer
  wants no clipping after turning Crosscut off.
- **Decision:** When Crosscut releases a view (turned off, or no plane), clipping is turned off.
  Pressing Alt+B while Crosscut is on still hands that new box to Blender.

### Changes after the maintainer's test of 0.3.0 (0.4.0, 2026-10-29)

- **Leftover Alt+B shading.** Blender shades the volume of an Alt+B box from the box itself, not
  from the clip planes, so it stayed when Crosscut took over. Crosscut now gives the view an
  empty box whenever it takes over (D-008 used to do this only when clipping was off). When
  Crosscut hands back, the user's planes come back and still clip, but their box shading
  doesn't: Python can't rebuild the box.
- **Overlaps: Blend / Stripes** in the Caps panel (D-018).
- **Cap Color** shows for Single, and for Auto only while some target is white or grey under the
  current Object / Material shading colour.
- **Interference** is a sub-panel of Caps with the on/off checkbox in its header: Style (Solid,
  Hatched, Cross), Color, Line Color and Opacity. Below 1, the blended or striped overlap shows
  through.
- Buttons now read Cursor / Center / Selection.
- The panel is now "Targets & Scrub Range", not the suggested "Scrub Targets & Range": Targets
  also decides which parts get caps, not just what the scrub range covers (*assumed*).

### D-018: Overlap stripes share the area by coverage order (2026-10-29)

- **Decision:** A pre-pass counts how many caps cover each pixel (a third 8-bit offscreen). The
  n-th cap drawn on a pixel keeps the stripes whose index mod that total equals n-1, so each of
  the overlapping parts gets an equal share. Stripes are twice the hatch spacing wide, in the
  hatch space, at the hatch angle minus 45 degrees (*assumed*; no separate width setting yet).
  Costs one extra mask pass per part, only where parts overlap.

### Changes after the maintainer's test of 0.2.0 (0.3.0, 2026-10-29)

Asked for in R-011 unless marked *assumed*:

- **Alt+B outlines ran past the box.** Blender clips the scene, not add-on drawing, and the fill
  was already trimmed to the other planes but the outline wasn't. Outlines are now clipped to
  the other active planes (`section_math.clip_segments`).
- **Dragging parts stuttered under Alt+B.** Alt+B gives six cap planes instead of one, so a
  moving part was cut six times per frame. Now (D-017): the box sides seen edge-on are skipped,
  a target is only cut by a plane where that plane's part inside the box can touch it, cap
  polygons are cached, and the triangle crossing test is about 4x faster. Two 160k-triangle
  parts dragged inside an Alt+B box: 15 ms a frame before, 4 ms now (13 ms once orbited so the
  sides are visible; Section is 7 ms).
- **UI** (D-013): Section / Slice buttons, either or neither on; cap style row below them, and
  it now also governs Alt+B (Backfaces = no caps anywhere), so "Cap Alt+B Clipping" is gone;
  axis row X Y Z Object View + Flip; scrub slider with the step arrows; Caps, Settings and
  Targets & Range panels collapsed. Settings holds Plane display, Readout, Scrub by Distance
  (shows the position as a distance instead of 0-1) and Step.
- **View plane** (D-014).
- **Backfaces + zero-thickness Slice** showed nothing. It now fills the section in the theme's
  Face Orientation back colour (darkened a little, *assumed*) with the usual outline.
- **Overlap colours** (D-015).
- **Plane tint / hatch** (D-016).
- **Defaults:** Hatch Space Model, Spacing 0.5. Scrub 0.5: the first time Crosscut is switched
  on the plane starts in the middle of the range, after that it stays where it was left.
  Changing the axis re-centres it (*assumed*: a position along X means nothing along Y).

### D-017: Cull cap planes that cannot show anything (2026-10-29)

- **Context:** Alt+B's six planes made every moving part six times as expensive as a Section.
- **Decision:** Skip native cap planes the view looks along (the four sides pass through the eye
  until you orbit: their caps have no area). For every plane, intersect it with the target's
  world bounding box, clip that polygon by the other planes, and skip the target if nothing is
  left. Cache cap polygons per section serial. Cache the triangle index columns per mesh.
- **Revisit if:** big parts still stutter when orbited; then a spatial index (Issue #4).

### D-016: Plane display None / Frame / Tint / Hatched, default Tint (2026-10-29)

- **Context:** The 1-pixel frame alone made it hard to see where the plane is.
- **Decision:** An enum in Settings. Tint fills the frame with 10 % amber; Hatched adds faint
  screen-space lines. Drawn before the caps, so caps paint over it and the kept part shows
  through it. Default Tint is *assumed*.

### D-015: Overlapping caps blend equally when interference is off (2026-10-29)

- **Context:** The last object drawn covered the others.
- **Decision:** Each cap's coverage is counted per pixel (8-bit offscreen, 16/255 per object, so
  up to 15 overlaps count exactly) and the n-th cap on a pixel is drawn with alpha 1/n: a running
  average, so all overlapping colours count equally. Complementary colours average to a greyish
  tone (blue + orange); striping each colour would keep them recognisable (open question).

### D-014: View plane is static, stored as normal + base (2026-10-29)

- **Decision:** The View button (operator `crosscut.from_view`) stores the view's direction and
  the middle of the targets along it; the plane does not follow the view, and clicking View
  again re-captures. Section keeps the far side, so you look straight at the cut, and scrubbing
  moves it toward or away from you. The pie's "Plane from View" (which added an Empty) became
  "Section from View" (*assumed*); the Empty is still available from Object > +.

### D-013: Section and Slice are two buttons, one or neither on (2026-10-29)

- **Context:** "Off" in the old mode row didn't say what was off, and the separate Alt+B toggle
  overlapped with Backfaces.
- **Decision:** Two operator buttons (`crosscut.set_mode`) drawn as toggles; clicking the lit one
  turns Crosscut off. The internal `mode` enum keeps OFF / SECTION / SLICE. The cap style applies
  to Section, Slice and Alt+B alike.

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
| Q-003 | Default cap style Hatched, 45 degrees, screen-space spacing 10 px | assumption | 0.1.0 | maintainer set Model space, 0.5 (R-011) |
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
| Q-014 | Screen-space vs. model-space hatching as default | unasked question | 0.1.0 | answered: Model (R-011) |
| Q-015 | Whether Material Preview support matters | unasked question | 0.1.0 | open |
| Q-016 | Whether a 6-plane section box is wanted | unasked question | 0.1.0 | open |
| Q-017 | Bugs from the maintainer's first test (details pending; first do our own Blender test pass) | follow-up | R-009 | done: first feedback in R-011 |
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
| Q-029 | Default hatch spacing 10 px looks denser than the mock-up on a large screen | unasked question | 0.2.0 | moot: default is now 0.5 in model space |
| Q-030 | Plane display defaults to Tint (D-016) | assumption | 0.3.0 | open |
| Q-031 | Pie "Plane from View" (Empty) replaced by "Section from View" (static View plane) (D-014) | assumption | 0.3.0 | open |
| Q-032 | Changing the axis re-centres the plane | assumption | 0.3.0 | open |
| Q-033 | Overlaps blend as an equal average; stripes of each colour might read better (D-015) | unasked question | 0.3.0 | answered: a Blend / Stripes toggle (R-012) |
| Q-034 | Backfaces + zero-thickness slice uses the theme's backface colour, darkened 25 % | assumption | 0.3.0 | open |
| Q-035 | Center / Cursor / Selection buttons stay in the main panel | assumption | 0.3.0 | kept; reordered Cursor / Center / Selection (R-012) |
| Q-036 | Stripe width = 2x hatch spacing, angle = hatch angle - 45 degrees; no own setting (D-018) | assumption | 0.4.0 | open |
| Q-037 | Panel named "Targets & Scrub Range" instead of "Scrub Targets & Range" | assumption | 0.4.0 | open |
| Q-038 | Next release numbered 0.4.0, not 1.0: 1.0 waits for the maintainer's go | assumption | 0.4.0 | confirmed: release after review (R-013) |
| Q-039 | Object auto-pick fills the plane object (only visible Empty, else only visible object) | assumption | 0.9.0 | open |
| Q-040 | Plane colours: amber first, blue second plane; tint opacity 10 % | assumption | 0.9.0 | open |
| Q-041 | The 1.0 candidate is numbered 0.9.0 | assumption | 0.9.0 | open |
| Q-042 | Whether to publish on the Blender Extensions platform for 1.0 | unasked question | 0.9.0 | open |
