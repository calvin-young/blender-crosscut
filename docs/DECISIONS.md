# Decisions and lessons

Why Crosscut is built the way it is, what didn't work, and what is still unconfirmed.
Newest entries first within each section. Keep each entry short.

## Requirements from the maintainer

What was actually asked for or explicitly discussed (2026-10-22 unless dated). Everything not on
this list is an assumption, tracked in the table at the end.

| ID | Requirement | Status in 0.1.0 |
| --- | --- | --- |
| R-021 | After 0.12.0 (2026-11-03): Measure in light blue at the cursor and a complementary color for the max, legible text, a toggle for the max; Clip Tint doesn't work (revert unless easy); "Fill Targets"; slices red on the back. Then: lit X/Y/Z/View turns off; weight painting doesn't work with clipping on; a way to adjust fill colors (grayer, redder, darker, transparent); Measure on single parts, thickness at the cursor, max optional and off, maybe an Ignore Overlaps toggle | 0.13.0, see below |
| R-022 | After 0.13.0 (2026-11-04): Brightness default 50 %; group the Cut Faces settings; a project-share pie on the status page; Measure: click anchors the end nearest the cursor, moving slides the other end along the contour, a second click pins it, repeatable, Esc clears. Asked for guidance on whether Measure should be a separate branch, release or add-on, and on dimensioned drawings | 0.14.0, see below |
| R-024 | After 0.15.1 (2026-11-04): first snap target for the free end, straight across from the anchor's edge; try 580 color on a real bucket and judge the lag by use; FDM as a placeholder for someone else to build; saved lines should follow a moved part unless pinned (being designed) | 0.16.0: snap (D-041), 580 color (D-042), FDM placeholder. Saved lines not started |
| R-023 | After 0.14.1 (2026-11-04): the free end must follow the cursor wherever it lands, or find the closest point on a curve, without overshooting; Esc shouldn't clear pinned lines at the first press; a Clear button and a way to keep them through Esc. Asked whether capturing Esc inhibits other Blender functionality | 0.15.0, see below |
| R-020 | After 0.11.0 (2026-11-03): no outlines through interiors in Print Preview; Slice looks the same as Section there; Slice Thickness into Section/Slice Plane; cursor, center, selection as small buttons between the arrows; even out the gaps around Measure Overlap, closer to Settings; settings for Measure Overlap (color, text size) and a local width at the mouse, on by default; is "Caps" too unintuitive; Clip Tint doesn't come back after off/on or after Section; left-align the three settings; back on its own tab, as a single panel | 0.12.0, see below |
| R-019 | After 0.10.0 (2026-11-03): outlines stay black on problem parts; a 0.5 button in the scrub row; Targets inside Caps as "Cap: Visible Objects..."; Interference becomes a third Overlaps option, Highlight, its settings right below; Plane renamed Section/Slice Plane with the scrub settings at its top; Clip remembers the last box; the release plan accepted, with no full release until the maintainer signals | 0.11.0, see below |
| R-018 | After 0.9.4 (2026-11-03): in development rather than test-only; a steering tally on the status page; guidance on releases; overlays off hide the plane; orange outlines stuck on; hatch scales with part size; caps match Random shading; move to the View tab with Settings folded in; annotations stay over caps; inside-out warning and a Face Orientation toggle; no "Alt+B" wording; drop the faint box, at least once scrubbing; two sliders or a toggle for the clip walls; an easy way to measure an overlap; a translucent cap seen from behind should read red like from outside | 0.10.0, see below |
| R-017 | After 0.9.3 (2026-11-02): a slider that slides the two Alt+B walls closest to parallel with the view along their normals, the box keeping its size (bounds and reset behaviour left to judgment); X/Y/Z/Object start a section while off; overlapping manifold shells inside one object must not cancel; Print Preview as a toggle under Settings for now | 0.9.4, see below |
| R-016 | After 0.9.2 (2026-11-02): put the plane row back while off (View is used to start a plane); Alt+B button first in the row and named Clip; fix the button staying lit after the Alt+B key; 1.0 is not close: keep user testing, and push back when bugs and features keep coming; download buttons on the status page. Asked whether vanilla Alt+B can be scrubbed | 0.9.3, see below |
| R-015 | Notes from using 0.9.1 on real work (2026-11-02): hide the axis row while off; align to an object's local XYZ; an Alt+B button; selected outline must win over a coincident black contour; readout hidden by the last-operation panel; Scrub by Distance and Step into Scrub Range, renamed Scrub Settings; X-ray should affect caps; Cap Targets right under Caps; Vary per Object must not change when parts are shown or hidden; warn when cutting through an open mesh even if the hole isn't on the plane, more severely when it is, and maybe lower the cap's opacity; "clashes on interference, both when enabled or disabled" | 0.9.2, see below |
| R-014 | After testing 0.9.0 (2026-10-29): plane tint default 0.03, slider 0 to 0.1 but typing up to 1; choosing Object with a plane object that's no longer visible must clear it (and pick the only visible object); show selection outlines in a zero-thickness slice; stop Blender's selection outline clashing with Crosscut's outline in a slab; move Caps and everything below into a separate, collapsed settings panel; line "Range" up with the Scrub Range row; list open follow-ups at the end of every reply | 0.9.1, see below |
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

### D-044: The header button goes beside X-ray by wrapping Blender's own helper (2026-11-09)

- **Context:** The maintainer asked for it between X-ray and the shading buttons. Add-ons can only add to a header's ends.
- **Decision:** Blender 5 draws X-ray with a module function, `bl_ui.space_view3d._toggle_xray_operator`. Crosscut wraps it
  (header region only, not the shading pie that also calls it) and puts it back when disabled. Blender 4.2 inlines that
  button, so there the button is appended at the right end as before.
- **Risk:** a private Blender function. If it's renamed, the button falls back to the right end; if its arguments change,
  the header could fail to draw. Another add-on wrapping the same function would stack, which is harmless.
- **Look:** it greys out with X-ray outside Solid and Wireframe (it still works), which fits: Crosscut can't clip there either.

### D-043: No clipping until the view has a clipping box (2026-11-09)

- **Crash:** with Edit Mode under Material Preview, Crosscut turned on: Blender 5.2 crashed in `ED_view3d_clipping_local`,
  reading `rv3d->clipbb`, which was null. `sync_clip` switched clipping on at once and left the box to `_prime` (D-008);
  `view3d.clip_border` refuses to run outside Solid and Wireframe, so the box never came, and Edit Mode's drawing reads it.
- **Decision:** a view without clipping waits, unclipped, until `_prime` has made the box, and `_prime` waits for Solid
  or Wireframe. Nothing is lost: Blender doesn't clip in Material Preview or Rendered.

### D-043: The demo reel's staging (2026-11-05)

- **Message:** CROSSCUT is a real part among the others, with a ramped underside (linear in x, so faces stay
  flat and the mesh closed), so a rising plane uncovers it left to right. The script picks the height in the build's
  lower half with the fewest parts in its footprint and takes those out (20 of 394).
- **Pointer:** screenshots have no mouse, so the reel draws one and calls Measure's own hover and click functions.
- **Overlap Max is off in the overlap shot:** on a plain rectangle it reads shorter than the width ([#15](https://github.com/calvin-young/blender-crosscut/issues/15)).

### D-042: 580 color: the GPU samples the textures, Python only carries the UVs (2026-11-04)

- **Context:** The issue suggested caching each image's pixels in numpy. On a real textured bucket that's 4.4 GB as
  Blender hands them over (float RGBA), 1.1 GB as bytes, before a single layer is drawn.
- **Decision:** `section_segments` reports which triangle corners each crossing came from (`crossings=True`), `crossing_values`
  turns that into UVs, and a band of quads along the contour is drawn with a shader that samples Blender's own GPU copy
  of the image (`gpu.texture.from_image`). Python never reads a pixel. The band sits inside the contour, using the
  segments' winding; a part with mixed normals gets it centered. Width: Color Depth, never below 2 pixels.
- **Measured** on a real 59M-triangle bucket with 252 parts and 40 textures, workstation, per scrub step once warm: 297 ms median
  without color, 386 ms with. First pass through: at worst 2.1 s while a texture uploads, against 21 s for the mesh read Print
  Preview already does. RAM up about 0.3 GB. Most of the time is the cut itself (issue #4), not color.
- **Cracks:** a quad per segment, each with its own direction, left thin cracks on dense meshes, so segments meeting at a point
  share one direction (`shell_inward`). It costs the extra 50 ms or so of the 89.
- **Limits:** only the bottom layer of a layered material; no color attributes; textures are read by the graphics card, so
  a weak one may struggle with a bucket's full set. Color Depth's 0.1 default is a guess (*assumed*).

### D-041: The free end snaps to straight across from the anchor's edge (2026-11-04)

- **Decision:** The normals come from the segment under the anchor, on either contour of an overlap, and both segments at a
  corner. It snaps with the mouse within 10 pixels of that line and more than 20 from the anchor (nearer than that, any direction
  would count). Inside the section the end goes to the first edge beyond the cursor, as `follow_cursor` does; outside, the
  crossing nearest the cursor. Ctrl turns it off, as Blender's snapping does; the key alone updates the line.
- **Limits:** on a faceted curve the normal is the facet's, not the true curve's. Other targets (vertices, midpoints, parallel to a
  pinned line) aren't built.

### Changes after the maintainer's notes on 0.14.1 (0.15.0, 2026-11-04)

- **The free end follows the cursor** (replaces D-037 and D-039's aim). The mouse's movement since the click was the
  wrong input, since it made the end lag behind where the cursor was. Inside the section, the line runs through the cursor
  to the first contour beyond it, past any walls before the cursor. Outside it, the nearest point on the contour,
  leaving out segments within 8 pixels of the anchor. Nothing moves until the mouse leaves the click by 4 pixels: the click
  is near the anchor, so it says nothing about where the end should go.
- **Esc** (D-040).
- **Text size follows Hatch Space**: `measure_text_height` in Model space (default 2 units, *assumed*), never below 7 pixels
  (*assumed*, so a far view stays readable); `measure_text_size` in Screen space.

### D-040: Pinned lines outlast the tool, and Esc clears them through a keymap entry (2026-11-04)

- **Decision:** Esc stops the Measure modal and leaves pinned lines. The next Esc reaches `crosscut.measure_clear`, a normal
  3D View keymap entry whose poll fails with no lines, so it costs other tools nothing, and the operator passes the
  event through under Keep Pinned Lines. A modal wasn't kept running for this: Blender postpones auto-save while
  any modal operator runs, so a tool left on would hold auto-save off for as long as lines were pinned.
- **Costs of the modal while Measure is on:** auto-save waits until it stops, and Esc goes to Measure first. A transform or
  other modal started during Measure gets Esc first, being newer.

### Changes after the maintainer's notes on 0.13.0 (0.14.0, 2026-11-04)

- **Cut Faces groups** (*assumed* order): which parts; their color (source, adjustments, opacities); the lines on
  them (hatching, outline); overlaps. Rules between them, no sub-panels.
- **Anchored lines** (D-037).
- **Measure stays in Crosscut for now** (D-038).

### D-039: An anchored line aims like a beam (2026-11-04)

- **Context:** D-037's nearest-point snap only reached an adjacent edge if the mouse went round the outside: with a
  line anchored mid-edge on a square, the free end stopped at the corner of the opposite edge.
- **Decision:** The free end's target still moves with the mouse, but the line aims from the anchor through it and
  stops at the first contour it meets. If it meets none, because it's aimed out of the part, it falls back
  on D-037's nearest point. This replaces D-037's rule while the line points into the part.

### D-038: Measure stays in Crosscut, no branch or second add-on (2026-11-04)

- **Context:** The maintainer wondered about a full release without it, with Measure on a branch or as its own add-on.
- **Decision (agreed by the maintainer):** Keep it on `main`, labelled experimental when a full release comes. It's
  off until clicked, so it can't get in anyone's way, and it reads Crosscut's cut contours, so apart from them it has
  nothing to stand on. Blender extensions have no dependency mechanism, so a second add-on would need to find Crosscut at
  run time and break when it changes. A long-lived branch means merging everything twice. `section_math` keeps the
  geometry separate, so splitting later stays possible.
- **Dimensioned drawings** are out of scope here (issue #10 closed): a possible add-on of its own some day,
  noted in the ai-context inbox and on the status page.

### D-037: A pinned line's free end moves by the mouse's movement, then snaps to a contour (2026-11-04)

- **Decision:** The click needn't be on the free end, so the free end moves as far as the mouse has since the click,
  then snaps to the nearest contour, leaving out segments passing within a quarter of the line's length of the anchor, so it
  can't fall onto the anchor's own wall. Over an overlap it keeps to the contour it started on. It clicks in place of
  selecting only when a line is showing, or one is being placed; other clicks pass through (*assumed*).
- **Limits:** pinned lines are temporary and in world space: not saved, and they don't follow a moved part or plane.

### Changes after the maintainer's notes on 0.12.0 (0.13.0, 2026-11-03)

- **Tools through a cut** (D-035).
- **Measure on single parts** (D-036). One button for both: what's under the mouse decides (*assumed*, as
  the maintainer suggested). Overlap Max stays on by default, Section Max off.
- **Clip Tint**: the orthographic prism was wrong. Rounding made a box's four parallel walls look as if they
  met far away, so the tint covered the whole screen, which looks like nothing. `lstsq` now ignores tiny
  singular values. Kept, since it was an easy fix and costs 12 triangles a frame, only when on.
- **Fill colors** (`fill_saturation`, `fill_brightness`, `fill_tint`, `fill_tint_amount`, `fill_opacity`):
  adjust colors that come from the parts, in linear. An explicit Fill Color is left alone, except for
  opacity. Defaults 0.75 and 0.75 (*assumed*: a cap is unlit, so at full strength it's brighter than
  the shaded surface beside it).
- **Lit axis buttons** turn off. View's re-capture on a second click (D-014) is gone from the panel; the pie
  still re-captures, since there it isn't a lit toggle (*assumed*).
- **Zero-thickness slice** never reads as a backface: it has no inside, and the side that read red was arbitrary.
- **Matcaps**: caps keep their color under a matcap, deliberately for now. They identify the part rather than
  show its surface.

### D-036: Thickness at the mouse is straight across from the nearest wall (2026-11-03)

- **Decision:** From the nearest point on the section's contour, through the mouse, to the far side, trying 15 degrees
  either way for the shortest. Left free to be shortest overall (as overlaps' local width is), the line cuts
  across a corner near one. Section Max erodes the island on a grid to its thickest place, then measures there.
- **Limits:** a part's own inner shells count as walls.

### D-035: A clipping box fitted for tools outside Object Mode (2026-11-03)

- **Context:** Weight paint, and other tools that call `ED_view3d_clipping_local`, test against the four sides of
  `rv3d->clipbb`, not `clip_planes`. D-008's empty box therefore clipped everything: painting did nothing with
  Section or Slice on since 0.1.0, or on a clipping region since 0.10.0 removed its box. Blender itself is fine.
- **Decision:** Outside Object Mode, whenever the planes change, fit a real box: for an instant, in one Python call,
  turn the view orthographic and line it up with the cut, run `view3d.clip_border` with the rectangle's sides on the
  cut and any free sides far away (`rv3d.update()` makes it take effect at once), and put the view back. Back in Object
  Mode the empty box returns. A clipping region drawn in perspective becomes a straight prism, slightly off at the
  far end. Its near and far faces mean nothing to these tools, which is why it's the sides that have to fit.
- **Drawback:** Blender tints that box on the background while outside Object Mode.

### Changes after the maintainer's notes on 0.11.0 (0.12.0, 2026-11-03)

- **Print Preview**: no contours except selected parts'. Slice wasn't a bug in the code: an opaque bed hides
  everything below the plane, so Section and Slice drew the same. Now Slice draws only the layer: the
  powder's surface, or with a thickness the bed between the slab's planes (*assumed* what Slice should mean).
- **"Caps" renamed** Cut Faces, its row Fill and its colour Fill Color (*assumed*: "caps" is jargon; a
  cut face is what a person sees). "Cap style" row labels are unchanged.
- **One panel, own tab** (reverses 0.10.0's View tab, maintainer's call). Settings and its sections are layout
  panels (D-033).
- **Local width** (D-034). **Clip Tint** (D-032).

### D-034: Local width is the shortest line through the mouse, one part's contour to the other's (2026-11-03)

- **Decision:** 60 directions through the point, each to the first contour hit either way; the shortest whose ends
  are on different parts, else the shortest of any. It reads as tangent to tangent, and near a corner it
  doesn't just cut the corner. Labels: "max" on the greatest depth. The same line twice shows once.
- **Limits:** a part's own inner shells count as contours (the eyes in a head), so a chord can stop at one.

### D-033: Settings as layout panels, not sub-panels (2026-11-03)

- **Context:** A sub-panel's gap from the main controls is Blender's and can't be changed.
- **Decision:** `layout.panel_prop` in the single panel, open state in `ui_*` properties. This shrinks the gap,
  and tests can open them to screenshot and draw them. Open state saves with the scene (*assumed* harmless).

### D-032: Crosscut draws its own clipping tint (2026-11-03)

- **Context:** Blender's tint comes from a box made when the region is drawn. Python can't rebuild it from the
  planes, so once gone (for scrubbing, or for Section) it couldn't come back.
- **Decision:** Blender's box is always swapped for an empty one (D-008). With Clip Tint on, Crosscut draws
  the region's volume itself: a prism of the four walls, only its far side, depth-tested, so it shows on the
  background as Blender's does. It follows a scrub (the earlier wish was for it to go on scrubbing; that was
  because Blender's couldn't follow, *assumed*). Colour is a very faint white, close to Blender's by eye.

### Changes after the maintainer's notes on 0.10.0 (0.11.0, 2026-11-03)

- **Dark outlines always** (replaces 0.10.0's red): warnings live in the readout only. So a part's open
  places aren't marked on the cut any more.
- **Highlight** replaces the `interference` switch: Blend under it, as when the highlight was on with
  Blend. Default Highlight, the old default look. The settings are just below the choice, so the
  Interference panel and the separate Scrub Settings and Cap Targets panels are gone.
- **Clip memory** (D-031).
- **Releases**, agreed: stay on 0.x with no 1.0 finish line; the middle number for features, the last for
  fixes; `main` always usable; branches only for big or risky work; a pre-release per build. A full
  release only when the maintainer signals it in the project's thread.
- The **Center** button stays in its row beside the new 0.5 button (*assumed*, asked in chat).

### D-031: Clip remembers the box Section or Slice replaced (2026-11-03)

- **Decision:** When Crosscut takes over a view with clipping on, it keeps those planes, per view. Clip
  brings them back on an empty box (D-008), so the tint doesn't come back. Lit, Clip removes the box and
  nothing is kept, which is the way to a new box; any new box replaces what was kept.
- **Limits:** in memory, not saved with the file (*assumed*).

### Changes after the maintainer's notes on 0.9.4 (0.10.0, 2026-11-03)

- **Version 0.10.0** (*assumed*): the 0.9 line suggested 1.0 was next, which it isn't. Numbering follows
  the release guidance proposed to the maintainer in chat; not yet agreed.
- **View tab**: `bl_category` is View; Settings is a sub-panel of the main panel.
- **Overlays off** hide the plane and the readout, with no setting (the maintainer left it to Claude's
  call). Caps and dark contours stay: they're the content, not an overlay (*assumed*).
- **"Stuck orange outline"**: *inferred, not reproduced with the maintainer's scene.* Selection colours
  already follow selection and overlays, but open contours were a fixed orange, so an open part looked
  permanently selected. They're now red, like the warning, and dark with overlays off.
- **Hatch scale** (`hatch_scale`, default 0.5 *assumed*): spacing x (part diagonal / 50) ^ scale, from the
  object's size, not the cut's, so hatching doesn't swim while scrubbing.
- **Random colours**: Blender's own hash (`OB` + name + NUL, mm2, int hash, HSV 0.5 / 0.8), checked
  against its pixels on 4.2 and 5.2. This could change if Blender changes it; the test would show.
- **Annotations** (D-029).
- **Inside out**: negative signed volume, for open meshes too (a threshold skips near-flat ones). Named
  in red with a red contour, and the cap stays. Closed with unbalanced edges = "flipped faces", amber.
- **A translucent cap from behind** (*assumed reading*): nothing draws caps red; the "red hatch" from
  outside is the green 50 % cap over a red backface. From behind, it's over nothing red, so it looked
  green. With Face Orientation on, a cap seen from the kept side now draws in the backface colour.
- **Wording**: the interface says Clip or Clipping Region. Docs name the Alt+B shortcut only where
  it's the shortcut. Internal identifiers changed to match (`crosscut.clip`).
- **Clip tint** (`clip_tint`, default off *assumed*): swapped for an empty box as in D-008, planes kept.
- **Clip sliders** (replaces the single slider in D-027): one per wall pair, always shown, labelled by nearest
  world axis (a label can repeat on a box drawn at 45 degrees), positive along it. Stable when
  orbiting, since the flipping direction and the jumping axis were the likely cause of "feels odd"
  (*assumed*). No auto-switching. The wheel still uses the axis facing the viewer, toward the viewer.
- **Measure Overlap** (D-030).

### D-030: Measure an overlap by hovering (2026-11-03)

- **Context:** The maintainer asked for a quick way to see how much two parts overlap: hover and see a
  line for the greatest distance between the two curves.
- **Decision:** A toggle (a modal that passes events through, so the viewport stays usable). It finds the
  overlap island under the mouse on a grid around it that grows until it holds the whole island (starting
  about 32 pixels across, so what's visible resolves), then takes the greatest distance from the island's
  boundary on one part to its boundary on the other, on the actual contours. Pure numpy in
  `section_math.overlap_span`. If one part is wholly inside, the other's whole contour is used.
- **Limits:** the first two parts where more overlap; a long thin island can break up on the grid
  (160 cells per side), and then only the piece under the mouse is measured. Overlaps inside one object
  aren't measured.
- **Alternatives considered:** exact polygon intersection (chaining contours and clipping: much more code
  for what's a reading); a permanent readout without a toggle (nothing can see the mouse without a modal).

### D-029: Draw annotations again, over the caps (2026-11-03)

- **Context:** Blender draws finished 3D annotations before add-ons' POST_VIEW drawing, and only the stroke in
  progress after. Caps paint over them, however depth is set.
- **Decision:** When caps are drawn, draw the visible layers' 3D strokes again last, with no depth test, in
  the layer's colour, width and opacity. Screen-space annotations are drawn later by Blender anyway.
  They lose Blender's onion skinning and pressure, which annotations' 3D strokes barely show. Follows
  overlays and the Annotations overlay toggle.

### Changes after the maintainer's review of 0.9.3 (0.9.4, 2026-11-02)

- **Overlapping shells** (D-028).
- **Alt+B scrub** (D-027).
- **Axis buttons while off** start the plane, in the last mode used, keeping the position if the axis
  hasn't changed. They run an operator while off because a property update can't see the view, which
  flipping to the cut side needs. Object with nothing to pick stays on Object and asks for one,
  rather than falling back to Z as a toggle used to.
- **Print Preview** merged from `mjf-preview` (D-022), as a sub-panel of Settings with its checkbox in
  the header (*assumed*: last in the list). The branch stays for the demo reel in `demo-reels`.

### D-028: Fill by winding number when normals allow it (2026-11-02)

- **Context:** D-003's even-odd rule makes two overlapping closed shells in one object cancel (a hole
  where a head and an eye overlap), while the same shells as separate objects fill. Slicers treat
  such overlaps as solid.
- **Decision:** Segments carry their direction from the triangle's normal. Fan triangles add to red or
  green in an extra offscreen by which way they face; a resolve pass lights the mask where the two
  differ, so nonzero winding counts as inside. Reversed inner shells still cut holes. Only for closed
  meshes where every edge is used equally in both directions; anything else (open, or a flipped
  face) stays even-odd, which doesn't depend on normals and doesn't streak. Each such part costs two
  more passes. Inner shells' contours are still drawn inside the fill: they're real edges, and
  they show there are overlapping shells.
- **Not done:** a self-overlap isn't flagged as interference; that's for separate objects only.

### D-027: Scrubbing an Alt+B box slides it rigidly, with no stored state (2026-11-02)

- **Decision:** The pair of opposite walls most facing the viewer picks the axis, recomputed on every
  read. The maintainer asked for those two walls to scoot; all the walls get the same translation, since
  in perspective the box's walls aren't parallel and the others must shift a little for the box to keep
  its shape. In orthographic the others don't change. The slider holds nothing: it reads where the box
  is along the current axis, so orbiting never moves the box or needs a reset, the slider just
  jumps to show the new axis (*assumed*). 0 and 1 are the box just clear of the Scrub Range (*assumed*),
  and positive is toward the viewer (*assumed*, like View). Right after drawing, all four walls are
  edge-on, so the slide is sideways on screen until you orbit (*assumed* acceptable).
- **Limits:** Blender's faint box tint comes from a box Python can't move, so it may stay behind.
  No undo per slide, as with the step buttons. Cursor, Center and Selection don't apply here.
- **Revisit if:** the maintainer's use says otherwise; this was explicitly a first guess.

### Changes after the maintainer's review of 0.9.2 (0.9.3, 2026-11-02)

- **Plane row** is back while off (reverses R-015's first item). X, Y, Z and Object still do nothing
  visible until Section or Slice is on, which was the original complaint; left as it is until the
  maintainer decides.
- **Clip button**: first in the row, named after Blender's "Clipping Region". The readout still says
  "Alt+B clipping" (*assumed*). The button went stale because the key only redraws the viewport;
  the draw callback now tags the area when the lit state changes.
- **1.0 is not close.** The maintainer called the 1.0 talk premature: keep testing on real work
  first. Version numbers stay 0.9.x, though they suggest otherwise (*assumed*; renumbering would
  confuse more).
- **Scrubbing a plain Alt+B box**: checked, not built. Its four side planes can be moved from
  Python and the caps follow; whether Blender's box tint follows wasn't checked ([issue](https://github.com/calvin-young/blender-crosscut/issues/9)).

### Changes after the maintainer's notes on 0.9.1 (0.9.2, 2026-11-02)

- **Interference clash** (D-023). The note was cut short; read together with its screenshot as the
  banding between overlapping caps (*assumed*).
- **Selected outline over a black contour** (D-024).
- **Local axes** (D-025).
- **Alt+B button** in the Section / Slice row, lit while the view has a box (*assumed*: a third
  button there, so one of the three lights up). Clicking it with Section or Slice on turns them
  off and waits for a box, unlike the Alt+B key, which only removes the clipping (*assumed*: a
  button labelled Alt+B should end up with a box).
- **Open meshes** (D-026).
- **X-ray**: caps multiply in the viewport's X-ray opacity, depth testing is off for fills and
  lines, and no depth is written. Contours stay opaque, like Blender's outlines in X-ray (*assumed*).
- **Vary per Object**: each part keeps an index for the session, handed out in name order over
  every solid in the scene, hidden ones too, so hiding changes nothing and a new part takes the
  next index. A name hash was rejected: two parts could get the same hatch. Hidden parts now use
  up indices, so two visible neighbours can (rarely) land on matching variations (six-step cycle).
- **Readout** bottom centre (*assumed*; moving it past the panel when one is showing would make
  it jump after every operation).

### D-026: Warn about open meshes wherever the hole is (2026-11-02)

- **Context:** A closed contour through an open mesh gets a confident solid cap and no warning,
  though the "solid" may not be material at all (Suzanne without her eyes).
- **Decision:** A mesh with any edge used by an odd number of triangles, matching vertices by
  position so unwelded shells still count as closed, is open. A cut through it warns in amber and
  draws the cap at Open Part Opacity, default 0.5 (*assumed*, as is the setting itself). An open
  contour on the plane warns in red and keeps its orange outline. Worked out once per mesh
  version, only for parts being cut: about 30 ms per 100k triangles, 300 ms per 1M.
- **Revisit if:** that cost shows in Edit Mode on heavy meshes.

### D-025: Local axes belong to the Object plane (2026-11-02)

- **Decision:** A Local Axis row (X, Y, Z, default Z, as before) under the plane object. No
  separate world/local switch, so all of Object's machinery still applies: it follows the object,
  and measures from its origin. Object now prefers the selected part when no single Empty is
  visible, since that's the usual reason to want its axes (*assumed*). **+** only reuses an Empty,
  so it can't move a part (a bug waiting to happen once parts were picked more often).

### D-024: A selected part flush with the plane still gets its contour (2026-11-02)

- **Context:** D-021 already has selected contours win over neighbours'. It missed a part with a
  face on the plane: the plane only touches it, so it has no section, and Blender's outline along
  that edge lies under the neighbour's black contour (our overlay draws after Blender's).
- **Decision:** For selected parts with no section, take one a millionth of the part's size to
  either side of the plane, and draw just its contour.
- **Not covered:** a selected part's silhouette that only lines up on screen with another part's
  contour, away from the plane. Fixing it needs the outline drawn by us or read back per pixel.

### D-023: Caps don't write depth as they draw (2026-11-02)

- **Context:** 0.9.1 made caps write depth (so a slab's far contour can't show through). Caps in
  one plane have different polygons, so rounding made them z-fight each other and the interference
  fill, in bands. Flat faces lying on the plane z-fought with the cap the same way, since 0.1.0.
- **Decision:** Fills draw with depth writes off and a small clip-space bias toward the viewer
  (1e-6, a few depth steps at any zoom). After a plane's fills, one colourless pass writes the
  depth of all its caps, unbiased, so contours keep their margin.

### Changes after the maintainer's test of 0.9.0 (0.9.1, 2026-10-29)

- **Plane tint opacity**: default 0.03; the slider runs 0 to 0.1 and typed values go up to 1.
- **Stale Object plane**: choosing Object when the plane object is hidden or no longer in the
  view layer clears it and picks again (only visible Empty, else only visible object, else none).
  Hiding the plane object while Object stays chosen keeps cutting with it (*assumed*: hiding a
  cutter Empty is normal; the reset is only when Object is chosen).
- **Selection outlines on cuts** (D-021).
- **Caps write depth**, so a slab's far contour can no longer show through its near cap. This
  was a thin dark line across the near cap, visible in the maintainer's slab, and it got mixed up
  with Blender's selection outline.
- **The plane frame is depth-tested** and lifted slightly toward the viewer, so parts and a
  slab's near cap hide it. It used to draw over everything.
- **Line colours were off**: Blender's built-in line shader takes sRGB and converts it itself,
  so the `_lin()` from D-009 made outline, open-contour orange and frame colours too dark and
  red. Lines now get sRGB; our own shaders stay linear (D-009 amended).
- **Panels**: the main panel holds only the controls you use while cutting. Everything else is
  in a separate top-level **Settings** panel, closed by default: Readout, Scrub by Distance and
  Step at the top, then sub-panels Caps (with Interference), Plane, Cap Targets and Scrub Range
  (*assumed* split: plane display got its own sub-panel). "Range" sits in the label column.

### D-022: Print Preview, on a branch (2026-10-30)

- **Context:** the maintainer wanted a view of what each layer physically looks like in an MJF
  printer (white powder, black fused cross-sections) for a demo video, and isn't sure it belongs
  in the 1.0 release.
- **Decision:** built on the `mjf-preview` branch. The powder is the bed box cut down to the kept
  side of the plane (`section_math.clipped_box_faces`), drawn opaque before the caps so it hides
  the parts below; the caps are drawn in the fused colour without hatching or interference.
  The surface on the plane writes no depth, so the caps in the same plane win without
  z-fighting (with Blender's default clip start a small offset still fought); the bed's sides do
  write depth. Grain is a hash of plane-local millimetres, faded out where it would be smaller
  than two pixels, so it doesn't shimmer.
- **Alternatives considered:** a separate add-on extending Crosscut (would need a public hook
  API); drawing it only in the demo script (no use to anyone else).
- **Revisit if:** the maintainer wants it in main, or as its own add-on.

### D-021: Selected parts' contours use the selection colour (2026-10-29)

- **Context:** Blender can't draw its selection outline for clipped geometry, so a
  zero-thickness slice showed no selection at all. In a slab, Blender's orange outline runs
  along the cut edge right next to our dark contour, which reads as a double line.
- **Decision:** a selected part's contour is drawn in the theme's Object Selected colour (the
  active object in Active Object), at least 2 px wide, after the other contours. It joins
  Blender's own outline along the cut instead of competing with it. It follows the viewport's
  overlay toggles (Overlays and Outline Selected), only in Object Mode, and draws even with
  Crosscut's Outline off (*assumed*: selection feedback shouldn't depend on a style option).
  A selected open (non-manifold) part shows the selection colour, not orange; the readout still
  names it.

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

### D-009: Colours sent to shaders are linear (2026-10-29; amended in 0.9.1)

- **Context:** Measured in 4.2 and 5.2: a fill of sRGB-intended 0.85 displayed as 237, i.e. the
  POST_VIEW overlay buffer is scene-linear and gets the display transform afterwards.
- **Decision:** All shader colours are linear. Object and material colours are used as stored;
  the Cap Color (COLOR_GAMMA), the palette and constants go through `_lin()`.
- **Amended (0.9.1):** this holds for our own shaders only. Blender's built-in
  `POLYLINE_UNIFORM_COLOR` takes an sRGB colour and converts it itself, so line colours are
  passed as sRGB (`_srgb()` converts linear object colours).

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
| Q-040 | Plane colours: amber first, blue second plane; tint opacity 10 % | assumption | 0.9.0 | colours open; opacity set to 3 % by the maintainer (R-014) |
| Q-041 | The 1.0 candidate is numbered 0.9.0 | assumption | 0.9.0 | open |
| Q-042 | Whether to publish on the Blender Extensions platform for 1.0 | unasked question | 0.9.0 | open |
| Q-043 | Selection-coloured contours draw even with Outline off, follow the viewport's Outline Selected overlay, Object Mode only | assumption | 0.9.1 | open |
| Q-044 | Settings layout: Readout, Scrub by Distance, Step at the top of Settings; Plane as its own sub-panel | assumption | 0.9.1 | open |
| Q-045 | A hidden plane object keeps cutting while Object stays chosen; it's only replaced when Object is chosen again | assumption | 0.9.1 | open |
| Q-046 | Plane frame hidden behind parts and the near cap (it used to draw on top of everything) | assumption | 0.9.1 | open |
| Q-047 | "Clashes on interference" (note cut short) means the banding between overlapping caps (D-023) | assumption | 0.9.2 | confirmed: fixed, per the maintainer |
| Q-048 | The Alt+B button turns Section/Slice off and waits for a box, unlike the key | assumption | 0.9.2 | confirmed by the maintainer |
| Q-049 | Local axes live under Object; Object prefers the selected part (D-025) | assumption | 0.9.2 | open |
| Q-050 | Open-part caps at 50 %, with a setting; the plane-crossing warning is red (D-026) | assumption | 0.9.2 | confirmed by the maintainer |
| Q-051 | In X-ray, contours stay opaque while caps go translucent | assumption | 0.9.2 | open |
| Q-052 | Readout at the bottom centre | assumption | 0.9.2 | open |
| Q-053 | Whether the black-over-orange case seen was the flush-face one (D-024) | unasked question | 0.9.2 | orange has won so far; the maintainer reports if not |
| Q-054 | The readout keeps "Alt+B clipping" while the button says Clip | assumption | 0.9.3 | answered: Clipping Region (R-018) |
| Q-055 | Alt+B scrub: slider reads the current axis, range to just clear of the Scrub Range, positive toward the viewer (D-027) | assumption | 0.9.4 | open |
| Q-056 | Print Preview is last in Settings, marked experimental | assumption | 0.9.4 | no longer experimental, per the maintainer (2026-11-04); its place in Settings is still open |
| Q-057 | Overlays off hide plane and readout but not caps or dark contours | assumption | 0.10.0 | open |
| Q-058 | The stuck orange outline was the open contour | assumption | 0.10.0 | moot: contours stay dark (R-019) |
| Q-059 | A cap seen from behind with Face Orientation on draws in the backface colour | assumption | 0.10.0 | confirmed by the maintainer |
| Q-060 | Clip Tint off by default; hatch Scale with Part 0.5 by default | assumption | 0.10.0 | open |
| Q-061 | Two fixed sliders for a clipping region, labelled by nearest world axis | assumption | 0.10.0 | feels good so far, per the maintainer |
| Q-062 | Numbering jumps to 0.10.0, and the release guidance in chat | unasked question | 0.10.0 | agreed (R-019) |
| Q-063 | A kept clipping box isn't saved with the file | assumption | 0.11.0 | open |
| Q-064 | "Caps" renamed Cut Faces, Cap to Fill | assumption | 0.12.0 | confirmed by the maintainer |
| Q-065 | Slice in Print Preview means one layer of powder, or a band | assumption | 0.12.0 | open |
| Q-066 | Our Clip Tint follows a scrub rather than disappearing | assumption | 0.12.0 | confirmed by the maintainer |
| Q-067 | Fill Saturation default 0.75 | assumption | 0.13.0 | open; Brightness set to 0.5 by the maintainer |
| Q-068 | One Measure button for parts and overlaps | assumption | 0.13.0 | open |
| Q-069 | The pie's Section from View still re-captures on a second click | assumption | 0.13.0 | open |
| Q-070 | Measure stays in Crosscut, no branch or second add-on (D-038) | unasked question | 0.14.0 | agreed by the maintainer |
| Q-071 | A click on a showing Measure line doesn't select; Esc while placing drops only that line | assumption | 0.14.0 | open |
| Q-072 | With the cursor beyond a wall, the free end goes past that wall to the edge beyond the cursor | assumption | 0.15.0 | feels great, per the maintainer |
| Q-073 | Pinned lines aren't saved with the file | assumption | 0.15.0 | being designed with the maintainer |
| Q-074 | Snap reach of 10 pixels; a marker at the anchor rather than a text label | assumption | 0.16.0 | open |
| Q-075 | Color Depth default 0.1 mm; never thinner than 2 pixels | assumption | 0.16.0 | open |
| Q-076 | A layered material shows its bottom layer only | assumption | 0.16.0 | open |
| Q-077 | The header button greys out with X-ray in Material Preview and Rendered | assumption | 0.16.1 | open |
