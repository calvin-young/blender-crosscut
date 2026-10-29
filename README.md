# Crosscut

Live, non-destructive **section** and **slice** views for Blender's 3D viewport.

Blender's clipping region (Alt+B) shows you the backfaces of whatever it cuts. Crosscut
uses the same viewport clip planes and adds **caps**: the cut is filled (and optionally
hatched) wherever the plane passes through solid material, so a cut part reads as a solid
cross-section, the way section views work in CAD. One key toggles back to the plain
backface look.

| Backfaces (plain Alt+B) | Hatched section | Slice |
|---|---|---|
| ![Backfaces](docs/images/screenshots/01_section_backfaces.png) | ![Hatched section](docs/images/screenshots/03_section_hatched.png) | ![Slice](docs/images/screenshots/04_slice_section_only.png) |

*Blender 5.2 screenshots made by [`tools/showcase.py`](tools/showcase.py). The look comes from
the maintainer's hand-made mock-ups in [docs/images/reference/](docs/images/reference/).*

## Features

- **Section**: cut along X, Y, Z, an Empty you place with G/R, or **View**: a plane facing the
  view as it is when you click, which stays put when you orbit (click again to re-aim).
- **Slice**: show only the cross-section (thickness 0) or a slab of any thickness.
- **Cap styles**: Backfaces (native look), Solid, Hatched. They apply to Section, Slice and
  Blender's own Alt+B box alike; Backfaces turns capping off everywhere.
- **Scrub**: drag a slider to sweep the plane across the targets' bounds, or across any
  object's bounds (for example a build volume), as 0-1 or as a distance. Step buttons and
  **Shift+Alt+Wheel** move it by a fixed step (default 0.08, one MJF layer at 1 unit = 1 mm);
  add Ctrl for 10 steps.
- **Plane display**: frame, tinted (default) or hatched, so you can see where the plane is.
- **Several bodies**: hatch direction then spacing alternates per object (ISO 128-50 style), and
  where two or more objects' sections overlap the overlap is cross-hatched in red
  (interference; style, colours and opacity adjustable). Overlapping caps either blend their
  colours or share the area in stripes.
- **Watertightness hint**: an open (non-manifold) section is outlined in orange and listed in the
  viewport readout.
- **Works with Alt+B**: Blender's own clipping box gets caps too. Pressing Alt+B while Crosscut
  is active hands clipping back to Blender (and turns Crosscut off).
- Colours follow the Solid shading colour (Object or Material); white or grey parts get the Cap
  Color (green by default) so the cut stands out. Or use a per-object palette or a single colour.
- A new section keeps the far side of the part, so you look at the cut face, not at the uncut
  outside. Flip swaps sides.
- Caps are drawn on the GPU every frame; the mesh/plane intersection is cached and only
  recomputed when the plane or the mesh changes (scrubbing a 1.3M-triangle mesh redraws in
  about 15 ms on the test machine). Nothing is added to or changed in your meshes.

| Several bodies with interference | Scrub range from a build-volume object |
|---|---|
| ![Several bodies](docs/images/screenshots/06_multibody_interference.png) | ![Range object](docs/images/screenshots/10_range_object_readout.png) |

## Install

Blender 4.2 or newer. Edit > Preferences > Get Extensions > (menu) > Install from Disk, pick
`crosscut-<version>.zip`.

## Use

| Where | What |
|---|---|
| **Shift+Alt+B** (3D View) | Pie: Section X / Y / Z, Off, Backfaces/Caps, Section/Slice, Flip, Section from View |
| Header button (right) | Toggle on/off, popover with the main controls |
| Sidebar (N) > Crosscut | Section / Slice, cap style, axis, scrub; Caps, Settings and Targets & Scrub Range below |
| **Shift+Alt+Wheel** | Step the plane (Ctrl for x10) while Crosscut is on |

Clipping and caps show in **Solid** and **Wireframe** shading (Blender does not clip Material
Preview or Rendered views). Objects displayed as Wire or Bounds, the plane object and the range
object are never capped, so a build-volume box does not fill the whole section.

## How it works

1. The plane(s) go into the view's `RegionView3D.clip_planes`, exactly the planes Alt+B sets, so
   everything (including selection) is clipped by Blender itself.
2. For each target, the evaluated mesh is intersected with the plane in numpy. Shared edges are
   evaluated in a canonical order, so the result is watertight even for unwelded STL-style
   meshes.
3. Each segment becomes a fan triangle from a common apex. Drawn into an offscreen mask with
   invert blending, a pixel flips each time it is covered and ends up lit exactly when it is
   inside the section (even-odd rule): holes and islands work without any triangulation or
   contour chaining.
4. A quad on the plane is drawn with the scene's depth buffer, keeping only lit mask pixels, and
   paints the fill and hatching. A second offscreen counts overlaps for interference.

### Alternatives considered

| Approach | Pros | Cons |
|---|---|---|
| **Clip planes + GPU caps (Crosscut)** | Live, non-destructive, Solid mode, exact section, interference | Needs closed meshes for clean caps; Solid/Wireframe only |
| Backface tint shader (material override) | Very cheap | Material Preview only, relies on normals, cannot show overlap or a section-only slice |
| Live boolean / bisect modifiers | Real geometry, renders anywhere | Slow on dense meshes, modifies the object stack |
| CPU contour triangulation | Real cap mesh, exportable | Chaining and hole handling are fragile on messy meshes; slower to scrub |

## Status

**Experimental (0.4.0).** 0.1.0 was written without access to Blender; 0.2.0 was the first build
run and tested in Blender, with an automated in-viewport test suite
([`tests/blender/`](tests/blender/run_viewport_tests.py)); 0.3.0 and 0.4.0 rework the UI and fix
what the maintainer's real tests found. Tested on Blender 4.2.23 LTS and 5.2.3 LTS (Linux, OpenGL;
5.2 also on Vulkan). Expect rough edges.

The project is developed almost entirely by an AI assistant (Claude) with minimal human code
review; the maintainer sets the direction, tests each build on real work and reviews the
behaviour and UI/UX. See [docs/PROMPT_STATS.md](docs/PROMPT_STATS.md) for how much human
steering went into it.

## Contributing

See [AGENTS.md](AGENTS.md) for setup, tests and layout, [CONTRIBUTING.md](CONTRIBUTING.md) for
how to report bugs and send changes, and [docs/DECISIONS.md](docs/DECISIONS.md) for why things
are built this way. Bugs and plans are in [Issues](https://github.com/calvin-young/blender-crosscut/issues).

## License

GPL-3.0-or-later, see [LICENSE](LICENSE).
