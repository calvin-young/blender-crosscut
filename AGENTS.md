# AGENTS.md

Guidance for AI coding agents (and humans) working in this repository.
The human-facing overview is in [README.md](README.md).

## Project at a glance

- **What it is:** a Blender add-on that adds filled (solid or hatched) caps to viewport
  clipping, plus section and slice views with a scrub slider. It drives the same
  `RegionView3D.clip_planes` that Alt+B uses and draws the caps with the `gpu` module.
- **Status:** experimental (0.1.0). The first build was written without access to Blender;
  the maintainer's first test found it "looks great but definitely buggy" (no details yet).
- **Runs in:** Blender 4.2+ as an extension (`crosscut/blender_manifest.toml`); Python 3.11
  inside Blender. `crosscut/section_math.py` and the tests run on any Python 3.10+ with numpy.

## Setup, test, package

- **Install for development:** link the package into Blender's user extension repo so edits
  are picked up on restart (or F3 > "Reload Scripts"):
  `ln -s "$PWD/crosscut" ~/.config/blender/<version>/extensions/user_default/crosscut`,
  then enable "Crosscut" in Preferences > Add-ons.
- **Run tests (no Blender needed):** `python tests/test_section_math.py && python tests/test_addon_logic.py`
- **Run in Blender with screenshots:** `blender --python tools/showcase.py` (needs a real
  display; viewport draw handlers do not run in `--background`). Writes PNGs to
  `~/crosscut_showcase/`.
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
  props.py ops.py ui.py   scene settings, operators, panels / pie / header popover / keymaps
tests/                    plain-Python tests; bpy/gpu are stubbed in test_addon_logic.py
tools/showcase.py         builds a demo scene in Blender and screenshots every mode
tools/concept_render.py   numpy ray caster used for the README concept figures
docs/                     DECISIONS.md, PROMPT_STATS.md, images (concepts + maintainer's reference mock-ups)
```

## Conventions

- **Units:** 1 Blender unit = 1 mm. Default step 0.08 = one MJF layer.
- Non-destructive: never modify user meshes, materials or modifier stacks.
- Draw callbacks must never raise every frame: catch, print once, show it in the readout.
- Never write ID data (scene properties etc.) from a draw callback; defer with `bpy.app.timers`.
  Writing `RegionView3D` clip planes from the draw callback is the current design; see
  docs/DECISIONS.md D-002 and its "revisit if".
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

## Before you change things

- Read [docs/DECISIONS.md](docs/DECISIONS.md): why it's built this way, what was tried, and the
  open assumptions the maintainer hasn't confirmed yet. Don't retry an abandoned approach
  without new information.
- The roadmap will live in GitHub Issues (not created yet; follow-ups are listed in DECISIONS.md).
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
