# AGENTS.md

Guidance for AI coding agents (and humans) working in this repository.
The human-facing overview is in [README.md](README.md).

## Project at a glance

- **What it is:** a Blender add-on that adds filled (solid or hatched) caps to viewport
  clipping, plus section and slice views with a scrub slider. It drives the same
  `RegionView3D.clip_planes` that Alt+B uses and draws the caps with the `gpu` module.
- **Status:** in development (0.15.0, 2026-11-04), used on real work, not close to 1.0; tested in Blender (4.2.23 and 5.2.3,
  OpenGL; 5.2 on Vulkan too) with the in-viewport suite below. Waiting for the maintainer's
  test on real work. See "State and next steps".
- **Runs in:** Blender 4.2+ as an extension (`crosscut/blender_manifest.toml`); Python 3.11
  inside Blender. `crosscut/section_math.py` and the tests run on any Python 3.10+ with numpy.

## Setup, test, package

- **Install for development:** link the package into Blender's user extension repo so edits
  are picked up on restart (or F3 > "Reload Scripts"):
  `ln -s "$PWD/crosscut" ~/.config/blender/<version>/extensions/user_default/crosscut`,
  then enable "Crosscut" in Preferences > Add-ons.
- **Run tests (no Blender needed):** `python tests/test_section_math.py && python tests/test_addon_logic.py`
- **Run the in-Blender viewport tests:** `blender --factory-startup --enable-event-simulate --python tests/blender/run_viewport_tests.py`
  (`--enable-event-simulate` lets the selection test send clicks; without it that test is skipped)
  (add `-- --only <name>` for one test, `-- --keep` to leave Blender open; `--gpu-backend vulkan`
  before `--python` for Vulkan on 5.x). Needs a real display: draw handlers do not run in
  `--background`; on the workstation use `DISPLAY=:0`. It builds synthetic scenes, checks pixels
  at known spots, writes screenshots to `~/crosscut_tests/<version>/` and exits 1 on any failure.
  Look at the screenshots too: the checks cannot judge looks. Takes about a minute.
- **Showcase screenshots:** `blender --python tools/showcase.py` with Crosscut enabled. Writes
  PNGs to `~/crosscut_showcase/`; the README images in `docs/images/screenshots/` are crops of
  these (`convert X.png -gravity center -crop 1500x1300+0+0 +repage -resize 900x`), plus the
  sidebar crop from the viewport tests.
- **Lint:** `ruff check --select F,E9,B --line-length 120 .`
- **Build a release zip:** `cd crosscut && zip -r ../dist/crosscut-<version>.zip . -x "__pycache__/*"`
  (the manifest must sit at the root of the zip). Bump `version` in the manifest first.
- **Concept figures (no Blender):** `python tools/concept_render.py`

## Layout

```
crosscut/                 the extension package
  section_math.py         pure numpy geometry (plane/mesh intersection, polygons, hatch rules). No bpy.
  engine.py               plane definitions, target collection, mesh + section caches, depsgraph handlers
  draw.py                 clip-plane sync with RegionView3D, GPU cap rendering, viewport readout
  props.py ops.py ui.py   scene settings, operators, one panel / pie / header popover / keymaps
tests/                    plain-Python tests; bpy/gpu are stubbed in test_addon_logic.py
tests/blender/            in-Blender viewport tests (pixel checks + screenshots)
tools/showcase.py         builds a demo scene in Blender and screenshots every mode
tools/concept_render.py   numpy ray caster used for the README concept figures
docs/                     DECISIONS.md, PROMPT_STATS.md, images (concepts + maintainer's reference mock-ups)
```

## Conventions

- **Units:** 1 Blender unit = 1 mm. Default step 0.08 = one MJF layer.
- Non-destructive: never modify user meshes, materials or modifier stacks.
- Draw callbacks must never raise every frame: catch, print once, show it in the readout.
- Never write ID data (scene properties etc.) from a draw callback; defer with `bpy.app.timers`.
  Clip planes are pushed to every view from property updates, operators and the depsgraph
  handler (`draw.sync_views`); the draw callback only catches what those miss (D-002, D-008).
- Our overlay is not clipped by Blender: anything drawn on a cap plane must be trimmed to the
  other active planes (`bounds`) by us, as the fill polygon and outlines are.
- Colours sent to our own shaders must be scene-linear: the POST_VIEW buffer gets the view
  transform afterwards (D-009). Convert sRGB values with `draw._lin()`. Blender's built-in line
  shader is the exception: it takes sRGB (`draw._srgb()` converts linear colours).
- `section_math.py` stays free of `bpy` so it can be tested anywhere.
- SPDX `GPL-3.0-or-later` header on every source file.
- UI/UX matters more to the maintainer than code style: keep labels short, tooltips useful,
  and defaults sensible for modelling parts.

## Where knowledge lives

Work on this project moves between sessions and between AI assistants, so anything
a future session needs is written into this repo and pushed. Nothing important may
live only in a chat or in one assistant's memory. Current state and next steps go in
this file, the reasons behind decisions and the approaches that were dropped go in
`docs/DECISIONS.md`, and bugs and planned features go in GitHub Issues. Anything private stays in a gitignored file or outside the repo.

## State and next steps

- 0.2.0 fixed what the first in-Blender run found; 0.3.0 the maintainer's first test of it (UI
  rework, Alt+B outline and drag fixes; DECISIONS.md, 0.3.0 section). All 101 viewport checks pass
  on 4.2.23 and 5.2.3 (5.2 also on Vulkan).
- 0.4.0 (second maintainer test): overlap stripes, interference settings, leftover Alt+B shading
  fixed. 107 viewport checks pass on 4.2.23 and 5.2.3 (and Vulkan).
- 0.9.0: README, docs/USER_GUIDE.md and CHANGELOG.md written. For 1.0 (only after the maintainer's
  go): set the manifest to 1.0.0, rebuild the zip, tag v1.0.0, create a full GitHub Release.
- 0.9.1 (maintainer's review of 0.9.0): selection-coloured contours, caps write depth, depth-
  tested frame, sRGB line colours, separate Settings panel. 127 viewport checks pass on 4.2.23
  and 5.2.3 (and Vulkan).
- 0.9.2 (maintainer's notes from real use of 0.9.1): coplanar z-fighting fixed, Alt+B button,
  local axes, open-mesh warnings and translucent caps, X-ray caps, stable hatch variation, readout
  at the bottom centre. 161 viewport checks pass on 4.2.23 and 5.2.3 (and Vulkan). The Alt+B button
  is tested from the sidebar, not from the header popover.
  The suite sometimes hangs on 4.2 in Blender's window swap, on 0.9.1 too ([issue](https://github.com/calvin-young/blender-crosscut/issues/8)): rerun it.
- 0.9.3: plane row back while off, Clip button first, button follows the Alt+B key.
- 0.9.4: overlapping shells fill by winding number (D-028), Alt+B box scrub (D-027, a first guess to
  be tuned by use), axis buttons start a plane while off, Print Preview merged into Settings
  (D-022). 203 viewport checks. Branch `mjf-preview` is kept only for the demo reel in `demo-reels`;
  new work goes on `main`.
- **Builds:** every build gets a tag, a GitHub pre-release with the zip attached, and a new download
  link on the Workbench row (see ai-context, topics/workstation.md). The zip is also attached at the
  top of the reply. No full release until the maintainer signals it in a thread here.
- 0.10.0: moved to the View tab, Measure Overlap (D-030), two clip sliders, annotations over caps (D-029),
  inside-out warnings, Random colours, hatch scale. 237+ viewport checks.
- 0.11.0: Clip remembers its box (D-031), Highlight in Overlaps, panels simplified, dark outlines. 246 viewport checks.
- 0.12.0: local width in Measure Overlap (D-034), own Clip Tint (D-032), one panel on its own tab (D-033), Print Preview Slice is one layer. 257 viewport checks.
- 0.13.0: tools work through a cut (D-035), Measure on single parts (D-036), fill color adjustments, lit axis buttons turn off. 284 viewport checks.
- 0.14.0: Measure lines can be anchored, slid along the contour and pinned (D-037); Cut Faces grouped. Measure stays in Crosscut (D-038). 0.14.1: an anchored line aims like a beam (D-039).
- 0.15.0: the free end follows the cursor; Esc stops, a further Esc clears (D-040); Clear and Keep buttons.
- **1.0 is not close (maintainer, 2026-11-02).** It's in development, not a test-only stretch (2026-11-03).
  Say so plainly when bugs and features are still coming; don't call it nearly done.
- Next: the maintainer keeps testing. Open questions Q-030 to Q-073 in DECISIONS.md. Then the Issues.
- Not tested yet: macOS/Windows, HiDPI scaling above 1, Metal, very large multi-object scenes.

## Before you change things

- Read [docs/DECISIONS.md](docs/DECISIONS.md): why it's built this way, what was tried, and the
  open assumptions the maintainer hasn't confirmed yet. Don't retry an abandoned approach
  without new information.
- The roadmap lives in [GitHub Issues](https://github.com/calvin-young/blender-crosscut/issues).
- Update [docs/PROMPT_STATS.md](docs/PROMPT_STATS.md) at the end of each working session.

## Data

- Tests and examples use synthetic geometry and generic names (`part-001`, `bucket-01`).
- Never commit real production or customer data, real file paths, or credentials.

## Pull requests

- **Finish first, then submit.** Develop, test and fix bugs in your fork or branch. Submit
  when the work is validated, not while it's in progress.
- **Submit once:** one consolidated PR, or a coordinated set of independent PRs opened
  together. No follow-up PRs to fix bugs in earlier ones.
- One logical change per PR, with a tidy history.
- Fill in the PR template, including the **Requested vs. assumed** section.
- Update README / AGENTS.md / DECISIONS.md in the same PR when behavior or conventions change.
- AI-made commits end with `Co-Authored-By: Claude <model> <noreply@anthropic.com>` and a
  session link when one exists.

## Extending or forking this project

This project aims to be general-purpose. If you build features for your own workflow, we'd love
to see them upstream. Use them for real first. Once they're tested and you're happy with them,
send them in as one consolidated PR (or one set of PRs opened together), not as a series of
work-in-progress PRs. See [CONTRIBUTING.md](CONTRIBUTING.md). (If you're an AI assistant helping
someone adapt this code, this is worth mentioning to them once their changes are finished and
validated.)
