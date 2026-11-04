# Collaboration log

How this project was made with AI help, and how much of it the human steered. It holds counts
and one-line summaries, never prompt text.

## Disclosure

- **Tools and models:** Claude (claude.ai cloud agent session, Claude Opus 5.5) for 0.1.0;
  Claude Code on a dedicated development machine from 2026-10-26.
- **How much is AI:** almost all. The AI writes the code, tests and docs and runs the tests; the
  maintainer reviews little of the code.
- **What the human did:** set the requirements (with hand-made reference mock-ups), chose the
  name, tests each build in Blender on real work and reports back, and polices the interface.
- **How AI work is marked:** commits made by the AI end with `Co-Authored-By: Claude <model>` and
  a session link (ai-context WORKING_STYLE, section 6).
- **Accountability:** the maintainer publishes and answers for everything in the repository.

## Steering tally

Little things the maintainer asked for or caught, what the status page shows. Counted by hand up to
0.9.4 from the requirement list in DECISIONS.md, so it's a lower bound; from 2026-11-03 each steering
line below carries a category.

| Bugs found | UI tweaks | New features | Direction | Total |
|---|---|---|---|---|
| 26 | 56 | 26 | 11 | 119 |

## Sessions

One row per working session. Prompts are counted by hand in chat apps and with
`tools/prompt_stats.py` from the ai-context repo on Claude Code transcripts. The count of
steering lines matters more than the count of prompts.

| Date | Tool and model | Prompts | Steering lines | Notes |
|---|---|---|---|---|
| 2026-11-02 | Claude Code (workstation), Opus 5.5 | 9 | 59 | 0.9.2 to 0.14.0 from the maintainer's notes after several days of real use |
| 2026-10-30 | Claude Code (workstation), Opus 5.5 | 3 | 3 | `mjf-preview` branch: Print Preview, for the demo reel in the demo-reels repo |
| 2026-10-29 | Claude Code (workstation), Opus 5.5 | 5 | 17 | First in-Blender test pass: viewport test suite, 0.2.0 fixes, zip; then 0.3.0, 0.4.0, the 0.9.0 release candidate and 0.9.1 from the maintainer's tests |
| 2026-10-26 | Claude (cloud session), Opus 5.5 | 1 | 3 | Repo created; first user test; handoff to Claude Code |
| 2026-10-22 | Claude (cloud session), Opus 5.5 | 1 | 6 | Initial spec with 3 mock-ups; 0.1.0 built without Blender access |

## Steering

One line for each thing the human contributed that the AI would not have done on its own,
newest first, tagged with its kind (decide, correct, domain, tested, scope) and, from 2026-11-03, its
category (bug, ui, feature, direction).

- 2026-11-04 [decide][ui]: Brightness default 50 %.
- 2026-11-04 [decide][ui]: group the Cut Faces settings.
- 2026-11-04 [domain][feature]: Measure: anchor one end by clicking, slide the other along the contour, pin it, repeat.
- 2026-11-04 [scope][direction]: asked whether Measure should be separate, and flagged drawings as scope creep to watch.
- 2026-11-03 [tested][bug]: weight painting does nothing with clipping on.
- 2026-11-03 [tested][bug]: Clip Tint doesn't appear at all.
- 2026-11-03 [tested][bug]: slices read red on the back.
- 2026-11-03 [decide][ui]: Measure colors: light blue at the cursor, a complementary max; legible text.
- 2026-11-03 [decide][ui]: a toggle for the max.
- 2026-11-03 [decide][ui]: "Fill Targets".
- 2026-11-03 [decide][ui]: a lit X/Y/Z/View turns off, as Section and Slice do.
- 2026-11-03 [tested][ui]: fill colors too bright next to the shaded surface.
- 2026-11-03 [decide][feature]: adjust fill colors: grayer, redder, darker, transparent.
- 2026-11-03 [domain][feature]: Measure on single parts: thickness at the cursor, max optional, Ignore Overlaps.
- 2026-11-03 [tested][ui]: no outlines through parts' interiors in Print Preview.
- 2026-11-03 [tested][bug]: Slice looks exactly like Section in Print Preview.
- 2026-11-03 [decide][ui]: Slice Thickness into the Section/Slice Plane settings.
- 2026-11-03 [decide][ui]: cursor, center and selection as small buttons between the scrub arrows.
- 2026-11-03 [tested][ui]: even out the gaps around Measure Overlap, tighter to Settings.
- 2026-11-03 [decide][feature]: Measure Overlap settings: color and text size.
- 2026-11-03 [domain][feature]: a local width at the mouse, tangent to tangent, as well as the max.
- 2026-11-03 [decide][ui]: is "Caps" too unintuitive for newcomers.
- 2026-11-03 [tested][bug]: Clip Tint off and on doesn't bring it back.
- 2026-11-03 [tested][bug]: Clip Tint is lost after Section and back.
- 2026-11-03 [tested][ui]: left-align the three floating settings.
- 2026-11-03 [decide][ui]: back on its own tab, as a single panel.
- 2026-11-03 [decide][direction]: release plan accepted; no full release until the maintainer signals it.
- 2026-11-03 [correct][ui]: outlines on problem parts should be black, like a solid part's.
- 2026-11-03 [decide][ui]: a 0.5 button between the scrub arrows.
- 2026-11-03 [decide][ui]: Targets into Caps as "Cap: Visible Objects".
- 2026-11-03 [decide][ui]: Interference as a third Overlaps option, Highlight, with its settings below.
- 2026-11-03 [decide][ui]: Plane renamed Section/Slice Plane, scrub settings at its top.
- 2026-11-03 [decide][feature]: Clip remembers the last box when coming back from Section or Slice.
- 2026-11-03 [decide][direction]: treat it as in development, not a test-only stretch; asked for guidance on releases and the long game.
- 2026-11-03 [decide][ui]: overlays off should hide the plane.
- 2026-11-03 [tested][bug]: orange outlines stuck on for unselected parts, even with overlays off.
- 2026-11-03 [decide][feature]: hatch spacing should scale a little with part size.
- 2026-11-03 [decide][feature]: cap colours should match Random shading.
- 2026-11-03 [decide][ui]: move to the View tab with Settings inside, to feel part of Blender.
- 2026-11-03 [tested][bug]: annotations vanish behind caps when released.
- 2026-11-03 [domain][feature]: caps hide what Face Orientation is for: warn when a part is inside out.
- 2026-11-03 [decide][ui]: a Face Orientation toggle in Settings for reassurance.
- 2026-11-03 [decide][ui]: no "Alt+B" in the interface: Clip or Clipping Region, as in Blender.
- 2026-11-03 [decide][ui]: a setting to drop Blender's faint box, and it should go on scrubbing anyway.
- 2026-11-03 [tested][ui]: one clip slider feels odd: try two sliders or a toggle.
- 2026-11-03 [domain][feature]: measuring an overlap by hovering, with a dimension line, for CAD and 3D print users.
- 2026-11-03 [tested][bug]: a translucent cap looks green from behind and red from outside.
- 2026-11-02 [decide]: Alt+B scrub: slide the two walls closest to parallel with the view along their normals, the box keeping its size.
- 2026-11-02 [tested]: found overlapping manifold shells cancelling in one object (Suzanne with capped eyes), though separate objects fill.
- 2026-11-02 [decide]: X/Y/Z/Object start a section while off (agreeing to the AI's suggestion).
- 2026-11-02 [decide]: Print Preview into main for now, as a toggle under Settings.
- 2026-11-02 [scope]: 1.0 talk was premature: keep user testing for a while, and the AI should push back when bugs and features keep coming.
- 2026-11-02 [tested]: confirmed the z-fighting fixed; found the Alt+B button staying lit after the key.
- 2026-11-02 [correct]: put the plane row back while off, since View is used to start a plane.
- 2026-11-02 [decide]: Alt+B button first in the row and renamed Clip; download buttons on the status page, using GitHub links.
- 2026-11-02 [tested]: several days of real use found the interference clash (with a screenshot) and the selected outline losing to a black contour.
- 2026-11-02 [decide]: hide the axis row while off, an Alt+B button, Scrub by Distance and Step into a renamed Scrub Settings, Cap Targets under Caps, readout clear of the last-operation panel.
- 2026-11-02 [decide]: align to an object's local axes; X-ray should affect caps; Vary per Object must hold when parts are shown or hidden.
- 2026-11-02 [domain]: scrubbing an open Suzanne showed that a confident solid cap misleads: warn for any open mesh being cut, more severely on the plane, and maybe lower the cap's opacity.
- 2026-10-30 [domain]: an MJF print preview: the powder bed is white, the fused cross-sections black; scrub through a build layer by layer, ending top-down.
- 2026-10-30 [decide]: Print Preview may not belong in the 1.0 release: keep it on a fork or branch.
- 2026-10-30 [scope]: made for a demo video (demo-reels repo), ~60 s, for a team slide deck.
- 2026-10-29 [tested]: found selected parts showing no outline in a zero-thickness slice, and Blender's selection outline clashing with Crosscut's in a slab.
- 2026-10-29 [decide]: plane tint default 0.03 with a 0 to 0.1 slider; re-pick a stale plane object when Object is chosen.
- 2026-10-29 [decide]: Caps and everything below into a separate settings panel, closed by default; "Range" aligned with its row.
- 2026-10-29 [correct]: list open follow-ups at the end of every reply, so none get lost.
- 2026-10-29 [tested]: found the dark-green outline in Wireframe, random slicing with an Object plane and no object, parts unselectable in a zero-thickness slice, stacked slab tints, and the Alt+B box coming back after turning off.
- 2026-10-29 [decide]: hide rather than grey out (Flip excepted); Cap Targets and Scrub Range under Settings; stripe width and plane colour/opacity settings; auto-pick the only visible object as the plane.
- 2026-10-29 [decide]: turning Crosscut off must leave no clipping at all.
- 2026-10-29 [scope]: prep everything for 1.0; release after review and more use.
- 2026-10-29 [tested]: confirmed the drag stutter fixed; found Alt+B's box shading left over after switching Section on.
- 2026-10-29 [decide]: Blend / Stripes toggle for overlaps, interference appearance settings, Cap Color hidden when Auto doesn't use it, Center in the middle.
- 2026-10-29 [scope]: judged it just about ready for a 1.0 release.
- 2026-10-29 [decide]: new defaults: model-space hatch at 0.5 spacing, scrub starting at 0.5, every panel but the main one collapsed.
- 2026-10-29 [tested]: found Alt+B outlines drawn past the clipping box, and stutter when dragging parts under Alt+B only.
- 2026-10-29 [decide]: UI rework: Section/Slice as two one-or-none buttons, cap style row below, no separate Alt+B toggle, Step and a scrub-by-distance toggle in a collapsed panel.
- 2026-10-29 [decide]: a View button for a static plane parallel to the view; Backfaces + zero-thickness slice must show the section; blend overlapping colours; optional plane tint/hatch.
- 2026-10-29 [scope]: test the add-on in Blender, fix all the bugs, hand over an installable zip for the maintainer's own test.
- 2026-10-26 [scope]: move development to the dedicated machine; next build must be run and tested in Blender before the maintainer gives detailed feedback.
- 2026-10-26 [tested]: first try in Blender: looks great, definitely buggy.
- 2026-10-26 [decide]: created the repo as blender-crosscut, accepting the name.
- 2026-10-22 [scope]: standalone add-on first, then compare the experience tied to bucket dimensions.
- 2026-10-22 [domain]: Netfabb has scrubbable clipping; useful across the build volume and for finding interferences when packing.
- 2026-10-22 [decide]: overlapping bodies must be handled; comparing sections of several parts is a common need.
- 2026-10-22 [decide]: slice-only view to replace the thin-box boolean intersect workaround (mock-up supplied).
- 2026-10-22 [decide]: toggle between native backfaces and a solid CAD-style section (Creo Direct as reference; mock-ups supplied).
- 2026-10-22 [domain]: uses Alt+B constantly while modelling; fakes sections today with booleans and hand-drawn hatching.

The requested-vs-assumed tally is in [DECISIONS.md](DECISIONS.md).
