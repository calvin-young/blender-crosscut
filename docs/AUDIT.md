# Audit of Crosscut 0.16.2 (2026-11-12)

A review only: nothing in the add-on was changed. Every source file in `crosscut/` was read in full.
The numpy tests pass, and the viewport suite passes on Blender 5.2.3 (327 checks, OpenGL, 1920x1080).
Findings marked **(reasoned)** follow from the code alone and were not reproduced in Blender; the fix
should start with a failing test or a measurement.

## Verdict

The approach is right. Driving Blender's own clip planes and filling the cut faces on the GPU with a
coverage mask is the robust way to get a live section view: no contour chaining, no triangulation, and
messy meshes still fill. The geometry in `section_math.py` is careful (canonical edge order gives
watertight contours on triangle soups) and well tested.

The weak side is scale. The add-on is tuned on one or a few parts, and its test scenes are small. A real
build has hundreds of parts, many of them copies of one mesh, and several costs grow with the number of
parts times something large: memory per copy, full-screen GPU passes per part, Python work per object per
redraw. Those are findings 1 to 4, and they matter most on the laptop this is meant for. There is no
benchmark that would have shown any of them (finding 14).

## Findings, ranked by impact

### Performance and memory

1. **Every copy of a mesh is cached separately.** `engine.py:346` keys the mesh cache by object, so 588
   keycaps that share one mesh are converted 588 times (`to_mesh`, triangles, `foreach_get`) and stored
   588 times. `engine.py:420-424` stores vertices as float64 and triangles as int64 twice (`t` and
   `cols`): about 60 bytes per triangle per object. A 100k-triangle part times 588 is about 3.5 GB, and
   the open / oriented / inside-out check (`engine.py:527`) also repeats per copy.
   *Fix:* for a `MESH` object with no modifiers and no shape keys, key by mesh data name, as
   `surface_corners` already does (`engine.py:490`); keep the per-object key otherwise. Store triangles
   once as int32 (drop `t`, keep `cols`; `section_math.py:113` must then stop forcing int64, which would
   copy on every call). Invalidate by data name on a mesh update. Expected: memory and first-draw time
   divided by the number of copies.

2. **GPU work per frame grows with parts times screen pixels.** For each part on a plane, `_draw_caps`
   clears a full-size mask (`draw.py:268`, `814`, `831`, `847`), and with several parts runs one or two
   full-screen passes (`_add_coverage`, `draw.py:853`; the winding resolve, `draw.py:845-850`; a second
   coverage loop for stripes, `draw.py:1164`). 300 parts on a 2560x1600 view is over 2 billion pixels a
   frame, before anything visible is drawn. On the workstation's Quadros this hides; on an integrated
   GPU it is likely the main cause of lag **(reasoned)**.
   *Fix:* bound every per-part pass to the part's own rectangle on the plane. Build one more cached
   batch per part, the unclipped bounding quad that `cap_polygon` already computes, and draw the clear
   (a zero-colour quad, blend off), the resolve and the coverage step with it and a `viewProj` vertex
   shader, in place of `_clear_bound()` and `_fullscreen_batch()`. The fan triangles always lie inside
   that quad, so it is exact. Cost then follows the screen area the parts cover, not parts times screen.

3. **The offscreen buffers are rebuilt whenever two 3D views differ in size.** `_offscreen`
   (`draw.py:254-265`) keeps one size and frees the rest, so two viewports (or a quad view with uneven
   regions) free and allocate four full-size buffers per region per redraw.
   *Fix:* keep a small dictionary by size (say six entries, least recently used freed).

4. **Python work per object on every redraw of every view.** `collect_targets` (`engine.py:319-349`)
   walks `depsgraph.object_instances` and builds a `Target`, a matrix copy and a `persistent_id` tuple
   for each, on each redraw, changed or not. `_frame_quads` and `bed_bounds` walk all objects again
   through `target_points` (`draw.py:1279`, `engine.py:300`), and `_selection_rank` calls `select_get`
   for every line twice (`draw.py:1241-1243`). A thousand objects cost tens of milliseconds a frame
   before any drawing **(reasoned)**.
   *Fix:* cache the target list per (view layer, 3D view, settings that pick targets) and drop it from
   the depsgraph handler and from the property updates; compute the selection rank once per target per
   draw.

5. **Scrubbing recomputes every vertex of every crossed part** (issue #4). `section_segments`
   (`section_math.py:117-122`) does a dot product over all vertices and three gathers over all
   triangles per part per plane move.
   *Fix:* per mesh and local plane direction, cache `verts @ n` (only the offset changes while
   scrubbing) and a slab index: a few hundred slabs along the direction, each listing the triangles that
   reach into it. A move then touches only the triangles near the plane. Keep the last two or three
   directions per mesh. Do this after 1, since the index belongs on the shared mesh entry.

6. **580 color lag** (issue #14), likely cause **(reasoned)**: `shell_inward` calls
   `np.unique(..., axis=0)` (`section_math.py:181`), which sorts rows through a slow path, on every
   plane move for every part. *Fix:* the byte-view trick already used in `open_endpoint_count`
   (`section_math.py:212-214`), with `return_inverse`. Measure before and after on one dense part.

7. **Open meshes hit a cliff.** `close_open_contours` (`section_math.py:249-275`) builds an all-pairs
   distance matrix for up to 4096 open ends: about 400 MB of temporaries and a 16-million-element sort,
   on every plane move through a badly open scan or STL. *Fix:* lower the limit to about 500, or pair
   ends through a grid of cells.

8. **Smaller leaks and repeats.** `_meshes`, `_surfaces`, `_crossings` and `_hatch_ids` are never
   pruned for deleted objects (`engine.py:354-358`; only `_sections` is, at `614`). `invalidate_object`
   scans every cache key, and the handler scans every object per changed mesh (`engine.py:362`, `633`).
   `hatch_index` re-sorts all scene objects for each new instance (`engine.py:383`). `prune` and the
   batch cleanup run per region (`draw.py:1262`), so two views showing different things evict each
   other's work.

### Correctness

9. **State keyed by a view's memory address is never cleaned up** **(reasoned)**. `_clip_state`,
   `_saved_clip`, `_tool_box`, `_clip_lit`, `_tint_gone` and `_last_info` use `rv3d.as_pointer()`
   (`draw.py:35-43`) and keep entries after an area closes, a workspace changes or a file loads
   (`engine.on_load`, `engine.py:646`, clears none of them). A new view that lands on a reused address
   inherits "Crosscut owns this view" with planes that don't match, which `sync_clip` reads as "the user
   pressed Alt+B" and switches Crosscut off (`draw.py:564-571`). That would look like Section turning
   itself off now and then after closing an area or opening a file. A file saved with Section on is a
   related case: on load the view's saved planes are taken for a user's clipping box and stored for the
   Clip button to bring back (`draw.py:573-574`).
   *Fix:* in `sync_views`, drop entries whose key is not among the current views; clear all of them on
   `load_post`. Add a test that saves with Section on, reloads, and checks it's still on and Clip has
   nothing stale to restore.

10. **Undo deletes pinned measurements and every cache.** `undo_post` and `redo_post` run `on_load`
    (`__init__.py:25-30`), which calls `measure_clear()` and `invalidate_all()` (`engine.py:646-651`).
    Pin three lines, move a part, press Ctrl+Z: the lines are gone, and a large build re-converts every
    mesh. *Fix:* a separate undo handler that only invalidates the mesh caches; pinned lines stay. This
    goes away properly once lines are saved in the file (#12).

11. **Instances may leave dangling references** **(reasoned, needs a test)**. `Target.eval_ob` keeps
    `inst.object` after the `object_instances` loop ends (`engine.py:329`, `347`) and `_mesh` calls
    `to_mesh` on it later. Blender documents instance objects as valid only during the loop. Collection
    instances have worked; a Geometry Nodes "Instance on Points" of a mesh that belongs to no object is
    the case to try. *Fix if it fails:* read the mesh inside the loop for instances.

12. **Measure: the local width can read longer than "max"** (issue #15). The two numbers come from
    different methods: "max" is the farthest nearest-distance between the two contours, sampled on a
    160-cell grid and thinned (`section_math.py:675-682`), and the local width is the shortest of 60
    chords through the mouse (`section_math.py:575-602`). Grid error alone lets local exceed max by up
    to a cell. *Fix:* after both are found, if local is longer, show the local line as the max (the code
    at `draw.py:1718` already merges them when they agree within 1 %); and refine "max" by running
    `_chord` at its point so both come from the same measurement.

13. **Controls assume they are drawn in a 3D view.** `_clip_view` (`props.py:84-90`), the Clip button
    state (`ui.py:16`), `crosscut.clip` (`ops.py`, `context.space_data.region_3d`), `crosscut.step`,
    `crosscut.from_view` and the Face Orientation row (`ui.py:247`) read `context.space_data` as a 3D
    view. In a quad view they act on one of the four regions only. This blocks #18 (see below).

### Tests

14. **No benchmark at build scale.** The `performance` and `drag_perf` tests use one dense sphere. Add
    `tools/bench.py`: 500 objects sharing three meshes (about 20k triangles each) inside a build-volume
    box, one and two viewports, reporting milliseconds per scrub step, milliseconds per redraw and
    process memory. Findings 1 to 5 each need a before and after from it. Run it on the laptop once;
    the workstation's GPUs hide finding 2.
15. **The viewport suite depends on a 1920x1080 window** and is one 2,800-line file; a 4K desktop
    failed two tests. Fine for now. The numpy tests are fast and should run in GitHub Actions (#6).
16. **Missing cases:** two add-ons drawing in the same view (#17), the panel in the Properties editor
    (#18), reload with Section on (finding 9), undo with pinned lines (10), a Geometry Nodes instance
    (11), many copies of one mesh (1).

### Architecture

17. **`draw.py` is 2,060 lines doing four jobs:** clip-plane ownership (lines 297-620), the cut-face
    renderer (697-1456), the Measure tool's state and drawing (1487-1800), and the readout (1889-2020).
    Each session that touches any of it has to load all of it. *Fix:* split into `clip_sync.py`,
    `caps.py`, `measure.py` and `readout.py` as a pure move, after the fixes above, with the suite as
    the safety net. Measure's state is a module-level dictionary with ten loosely related keys
    (`draw.py:44`); make it a small class while moving it.
18. **The clipping-box workarounds are the fragile core** (`_prime`, `_remove_tints`, `_fit_tool_box`,
    `draw.py:340-483`): they run `view3d.clip_border` with an empty rectangle, and for tools they move
    the view for a moment to make Blender build a box. They are forced by Blender not exposing the box
    to Python. With more time, the real fix is a small patch to Blender that lets Python switch clip
    planes on without a box; until then, leave them alone and keep their tests.

### UX and wording

19. **Leftover "cap" wording**, against D-045: the readout's "Not capped (Wire/Bounds display)"
    (`draw.py:1949`; the panel says "Not filled"), "excluded from capping" (`props.py:413`), and the
    Settings panel property named "Measure Overlap" (`props.py:252`).
20. **A placeholder ships in the UI:** Printer > FDM "Not built yet" with a link button
    (`props.py:430`, `ui.py:227`). Remove the entry until someone builds it; the issue is enough.
21. **Print Preview's printer list is a fourth printer list.** Under portfolio decision D2 it should
    read the shared printer file and keep only "what a fused layer looks like" as its own setting.
22. **Settings holds about sixty controls.** Most are rarely touched. Candidates to drop or fold:
    Fill Tint and Tint Amount, Stripe space and widths, the second max colour. Worth one pass with
    Calvin over which ones he has ever changed.
23. **README says 0.16.0** in Status; the manifest is 0.16.2.

## #17 draw order, checked against portfolio decision D4

The cause is certain from the code. Crosscut paints each cut face testing only against the scene's depth
(`draw.py:1187-1196`). Bucket Builder's overlay writes no depth. So when Crosscut's handler runs after
Bucket Builder's, the cut faces paint over its lines everywhere, in front or behind. In the other order
it is already correct: Crosscut writes the cut faces' depth afterwards (`_write_cap_depth`,
`draw.py:942`), and Bucket Builder's depth-tested lines are then hidden only where they are behind one.

D4's rule (scene layer writes depth, annotations draw after and never write depth) is right, and
Crosscut already follows its half. But D4's remedy, moving always-visible annotations to `POST_PIXEL`,
covers only those. Bucket Builder's bounds are meant to be hidden by parts, so they need the depth test,
and they still need to draw after the cut faces. **Order has to be settled, not avoided.**

Proposed mechanism, about twenty lines copied into each add-on (rules shared, not code, as in D1):

- A registry held in `sys.modules` under one agreed name (it must survive file loads, which
  `bpy.app.driver_namespace` does not): add-on name -> (layer number, a function that removes and re-adds
  that add-on's `POST_VIEW` handler). Scene layer = 0, annotation layer = 100.
- On register, an add-on adds its handler, enters itself, then calls the re-add function of every entry
  with a higher layer number, lowest first. Handlers then run in layer order whichever add-on loaded
  first. On unregister it removes its entry. A re-add function that raises is dropped.
- Each add-on still works alone, and a third add-on joins by copying the same lines.

Inside Crosscut: nothing else needs to change for #17. Its own Measure lines, annotations redraw and
readout already draw after the cut faces without depth. Test: a stand-in handler that draws a
depth-tested line across a cut face, registered before and after Crosscut, with a pixel check both ways;
plus one screenshot with the real Bucket Builder in each order.

This amends D4, so it needs the Bucket Builder session's agreement on #28 before either side builds it.

## #18 panel location, checked against portfolio decision D3

D3's design is sound: `panel_location` ("Sidebar" by default, or "Scene Properties") and `sidebar_tab`
(text, default "Crosscut") in the add-on preferences, the panel class re-registered on change. I agree
with D3's pushback that `panel_location` is a trial setting to remove once Calvin has picked.

What it takes in Crosscut, beyond moving the class:

- **A view resolver.** One helper returning (area, region, space, rv3d): the context's own 3D view, or
  else the largest 3D view on the screen. Everything in finding 13 goes through it, and the operators
  that need a viewport (`clip`, `from_view`, `step`, `measure`, `add_plane`) run under
  `temp_override` for that view. With no 3D view on screen, the view-dependent rows show one line saying
  so.
- **The warnings at the bottom of the panel** read the last draw's info by region (`ui.py:274`); use the
  resolved view's region.
- **The header button and the pie stay** where they are in both settings.
- **In the Scene tab** the panel should start closed (`DEFAULT_CLOSED`), since that tab is long.
- Tests: draw the panel in both places with no errors, and press Clip, an axis button, Step and Measure
  from a Properties editor.

## What to build, in order

1. `tools/bench.py` (14), so the rest can be measured.
2. Shared mesh cache and int32 triangles (1); bounded GPU passes (2); offscreen sizes (3).
3. Stale view state (9) and undo (10), each with its test.
4. #17 once agreed with Bucket Builder; #18 with the view resolver (13).
5. Cached targets (4), the `np.unique` fix (6), the open-contour limit (7), cache pruning (8), #15 (12).
6. The slab index for scrubbing (5, closes #4).
7. Wording and README (19, 20, 23); the `draw.py` split (17) last.

## Where I'd push back

- **`panel_location`** should be temporary (D3 says the same).
- **D4 as written doesn't fix #17** for depth-tested annotations; see above.
- **Saving Measure lines in the file (#12)** is worth more than it looks: it removes the undo loss (10)
  and makes Measure a record, not a glance. I'd put it ahead of FDM, 580 polish and any new Print
  Preview work.
- **1.0 should wait for the build-scale benchmark**, not for more features: the feature set is ahead
  of the proof that it stays fast on a full bucket on the laptop.

## Requested vs. assumed

- **Requested:** an audit, review only, with ranked findings, file and line, and a proposed fix each; a
  check of #17 and #18 against D3 and D4.
- **Assumed:** that findings marked (reasoned) may go in without being reproduced, given the budget; the
  build order above; the registry mechanism for #17, which nobody has agreed to yet.
- **Questions not asked:** how many parts and triangles Calvin's usual builds have in Blender, and
  whether the lag he has seen is on the laptop; which Settings controls he has ever changed.
- **Follow-ups:** agree the draw-order mechanism on #17 and bucket-builder #28; one laptop run of the
  benchmark once it exists.
