# SPDX-License-Identifier: GPL-3.0-or-later
"""In-Blender viewport tests for Crosscut: real drawing, pixel checks, screenshots.

Needs a real display (draw handlers do not run in --background) and Crosscut
installed in the user extension repo (see AGENTS.md):

    blender --factory-startup --python tests/blender/run_viewport_tests.py

Options after `--`:
    --out DIR      where screenshots go (default ~/crosscut_tests/<blender version>)
    --keep         leave Blender open at the end
    --only NAME    run only tests whose name contains NAME

Builds synthetic scenes, steps through modes and settings, checks pixels at
known spots (cap colour inside the cut, background outside it, ...), writes a
screenshot per check, and exits with status 1 if a check fails or Crosscut
printed a traceback.
"""

import math
import os
import sys
import time
import traceback

import bmesh
import gpu
import bpy
import numpy as np
from bpy_extras.view3d_utils import location_3d_to_region_2d
from mathutils import Euler, Vector

MODULE = "bl_ext.user_default.crosscut"

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def _opt(name, default=None):
    if name in argv:
        i = argv.index(name)
        return argv[i + 1] if i + 1 < len(argv) else True
    return default


VERSION = "%d.%d" % bpy.app.version[:2]
OUT = _opt("--out") or os.path.join(os.path.expanduser("~"), "crosscut_tests", VERSION)
ONLY = _opt("--only")
KEEP = "--keep" in argv

GREEN = (0.0, 0.85, 0.0)        # SINGLE cap colour used for pixel checks (sRGB, shows as 0,217,0)
BG_TOL = 18                     # max channel distance to count as "background"

results = []                    # (test, check, ok, detail)
_cc = {}


def cc(name):
    """Crosscut submodule."""
    if not _cc:
        import importlib
        for sub in ("draw", "engine", "ops", "props", "ui"):
            _cc[sub] = importlib.import_module(MODULE + "." + sub)
    return _cc[name]


# ------------------------------------------------------------------ geometry

def _link(name, me, loc=(0, 0, 0), color=(0.8, 0.8, 0.8)):
    ob = bpy.data.objects.new(name, me)
    ob.location = loc
    ob.color = (*color, 1.0)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def hollow_sphere(name, r_out, r_in, loc=(0, 0, 0), color=(0.8, 0.8, 0.8), segs=64):
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=segs, v_segments=segs // 2, radius=r_out)
    inner = bmesh.ops.create_uvsphere(bm, u_segments=segs, v_segments=segs // 2, radius=r_in)
    inner_faces = list({f for v in inner["verts"] for f in v.link_faces})
    bmesh.ops.reverse_faces(bm, faces=inner_faces)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for p in me.polygons:
        p.use_smooth = True
    return _link(name, me, loc, color)


def box(name, size, loc=(0, 0, 0), color=(0.8, 0.8, 0.8), open_top=False):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=Vector(size), verts=bm.verts)
    if open_top:
        top = max(bm.faces, key=lambda f: f.calc_center_median().z)
        bmesh.ops.delete(bm, geom=[top], context='FACES_ONLY')
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    return _link(name, me, loc, color)


def cylinder(name, radius, depth, loc=(0, 0, 0), color=(0.8, 0.8, 0.8), segs=64):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=segs, radius1=radius, radius2=radius, depth=depth)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    return _link(name, me, loc, color)


def dense_sphere(name, subdiv, radius=30.0):
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=subdiv, radius=radius)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    return _link(name, me)


# -------------------------------------------------------------------- viewport

class View:
    def __init__(self):
        self.window = bpy.context.window
        self.area = max((a for a in self.window.screen.areas if a.type == 'VIEW_3D'),
                        key=lambda a: a.width * a.height)
        self.space = self.area.spaces.active
        self.region = next(r for r in self.area.regions if r.type == 'WINDOW')

    @property
    def rv3d(self):
        return self.space.region_3d

    def look(self, target, distance, rot_deg, ortho=False):
        rv = self.rv3d
        rv.view_location = Vector(target)
        rv.view_distance = distance
        rv.view_rotation = Euler([math.radians(a) for a in rot_deg]).to_quaternion()
        rv.view_perspective = 'ORTHO' if ortho else 'PERSP'

    def px(self, co):
        """Region pixel coordinate of a world point."""
        p = location_3d_to_region_2d(self.region, self.rv3d, Vector(co))
        return None if p is None else (int(round(p.x)), int(round(p.y)))

    def override(self):
        return bpy.context.temp_override(window=self.window, area=self.area, region=self.region)


def redraw(n=3):
    for _ in range(n):
        bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)


def settle(delay=0.05):
    """Let Blender run timers and handlers (as it would between user actions), then redraw."""
    yield delay
    redraw()


class Shot:
    """A screenshot of the 3D view area with pixel access in region coordinates."""

    def __init__(self, view, name):
        os.makedirs(OUT, exist_ok=True)
        self.path = os.path.join(OUT, name + ".png")
        with view.override():
            bpy.ops.screen.screenshot_area(filepath=self.path)
        img = bpy.data.images.load(self.path, check_existing=False)
        w, h = img.size
        buf = np.empty(w * h * 4, dtype=np.float32)
        img.pixels.foreach_get(buf)
        bpy.data.images.remove(img)
        self.px = (buf.reshape(h, w, 4)[:, :, :3] * 255.0 + 0.5).astype(np.int32)
        self.w, self.h = w, h
        # region offset inside the area screenshot (screenshot origin = area origin, bottom-left)
        self.ox = view.region.x - view.area.x
        self.oy = view.region.y - view.area.y

    def at(self, xy, r=1):
        """Median colour of a (2r+1)^2 patch at region pixel xy."""
        x, y = xy[0] + self.ox, xy[1] + self.oy
        patch = self.px[max(y - r, 0):y + r + 1, max(x - r, 0):x + r + 1].reshape(-1, 3)
        return tuple(int(v) for v in np.median(patch, axis=0))


def bg_of(shot, view):
    return shot.at((view.region.width // 2, view.region.height - 60), r=3)


def near(c, ref, tol):
    return max(abs(a - b) for a, b in zip(c, ref, strict=False)) <= tol


def is_green(c):
    return c[1] > 120 and c[1] > c[0] + 60 and c[1] > c[2] + 60


def is_red(c):
    return c[0] > 140 and c[0] > c[1] + 60 and c[0] > c[2] + 60


def is_greyish(c, lo=90):
    return max(c) - min(c) < 25 and min(c) >= lo


def check(test, name, ok, detail=""):
    results.append((test, name, bool(ok), detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {test}: {name} {detail}")


# ------------------------------------------------------------------ scenes

def new_scene(name):
    # start clean so object names stay as given (part-001, not part-001.004)
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    for me in list(bpy.data.meshes):
        bpy.data.meshes.remove(me)
    for co in list(bpy.data.collections):
        bpy.data.collections.remove(co)
    scene = bpy.data.scenes.new(name)
    bpy.context.window.scene = scene
    scene.unit_settings.system = 'METRIC'
    scene.unit_settings.scale_length = 0.001
    scene.unit_settings.length_unit = 'MILLIMETERS'
    return scene


def setup_view(view):
    sp = view.space
    sp.shading.type = 'SOLID'
    sp.shading.color_type = 'OBJECT'
    sp.shading.light = 'STUDIO'
    sp.overlay.show_floor = False
    sp.overlay.show_axis_x = False
    sp.overlay.show_axis_y = False
    sp.overlay.show_cursor = False
    sp.overlay.show_extras = False
    sp.clip_start = 0.1
    sp.clip_end = 100000.0
    view.rv3d.use_clip_planes = False


def settings(s, **kw):
    base = dict(mode='OFF', orientation='Z', offset=0.0, flip=False, thickness=0.0,
                cap_style='SOLID', targets='VISIBLE', color_source='SINGLE', single_color=GREEN,
                hatch_vary=True, interference=True, outline=True, plane_display='NONE',
                show_readout=True, range_source='TARGETS', range_object=None,
                hatch_space='SCREEN', hatch_pitch_px=10.0, scrub_distance=False, overlap_style='BLEND',
                interference_style='CROSS', interference_opacity=1.0)
    base.update(kw)
    for k, v in base.items():
        setattr(s, k, v)


def errors():
    return sorted(cc("draw")._errors)


# -------------------------------------------------------------------- tests
# Each test is a generator; `yield seconds` hands control back to Blender (so
# timers, depsgraph updates and normal redraws run) before continuing.

TESTS = []


def test(fn):
    TESTS.append(fn)
    return fn


@test
def section_caps(view):
    T = "section_caps"
    scene = new_scene("cc-section")
    hollow_sphere("part-001", 40, 25)
    s = scene.crosscut
    view.look((0, 0, 0), 220, (55, 0, 30))
    yield 0.1

    # Section Z through the middle; viewer is above, so the kept half must be
    # the far one: keep z <= 0 means the top half is cut away.
    settings(s, mode='SECTION', orientation='Z', offset=0.0)
    yield from settle()
    shot = Shot(view, "section_z_solid")
    bg = bg_of(shot, view)
    check(T, "crosscut owns clipping", view.rv3d.use_clip_planes and cc("draw").last_info(view.region).get("ours"))
    check(T, "top of sphere clipped (background)", near(shot.at(view.px((0, 0, 39))), bg, BG_TOL),
          f"{shot.at(view.px((0, 0, 39)))} vs bg {bg}")
    ring = (0, -32, 0)
    check(T, "cap colour on the annulus", is_green(shot.at(view.px(ring))), f"{shot.at(view.px(ring))}")
    c = shot.at(view.px(ring))
    check(T, "cap shows the Cap Color as picked (sRGB 0,217,0)", near(c, (0, 217, 0), 6), f"{c}")
    ring2 = (32, 0, 0)
    check(T, "cap colour on the annulus (side)", is_green(shot.at(view.px(ring2))), f"{shot.at(view.px(ring2))}")
    hole = (0, 0, 0)  # centre of the hole: the inner shell shows through it
    c = shot.at(view.px(hole))
    check(T, "hole shows inner surface, not cap", not is_green(c) and not near(c, bg, BG_TOL), f"{c}")
    outside = (0, -60, 0)
    check(T, "background outside the part", near(shot.at(view.px(outside)), bg, BG_TOL))

    # Flip keeps the top half: the cap faces away from the viewer and is
    # hidden by the outer shell, the bottom pole is clipped.
    settings(s, mode='SECTION', orientation='Z', offset=0.0, flip=True)
    yield from settle()
    shot = Shot(view, "section_z_flipped")
    check(T, "flip: top pole visible", not near(shot.at(view.px((0, 0, 39.5))), bg, BG_TOL))

    # Offset moves the cut
    settings(s, mode='SECTION', orientation='Z', offset=20.0)
    yield from settle()
    shot = Shot(view, "section_z_offset20")
    r = math.sqrt(40 ** 2 - 20 ** 2) - 3  # just inside the outer contour at z=20
    check(T, "offset: cap at z=20", is_green(shot.at(view.px((0, -r, 20)))), f"{shot.at(view.px((0, -r, 20)))}")

    # Hatched: mix of fill and darker lines inside the cap
    settings(s, mode='SECTION', orientation='Z', offset=0.0, cap_style='HATCH')
    yield from settle()
    shot = Shot(view, "section_z_hatched")
    cx, cy = view.px((0, -32, 0))
    cols = [shot.at((x, cy), r=0) for x in range(cx - 60, cx + 60)]
    greens = sum(is_green(c) for c in cols)
    darks = sum(max(c) < 80 for c in cols)
    check(T, "hatch: fill and lines both present", greens > 5 and darks > 3, f"green {greens} dark {darks} min {min(cols, key=max)}")

    # Backfaces: no cap, the inside of the shell shows
    settings(s, mode='SECTION', orientation='Z', offset=0.0, cap_style='BACKFACES')
    yield from settle()
    shot = Shot(view, "section_z_backfaces")
    check(T, "backfaces: no cap colour", not is_green(shot.at(view.px(ring))))

    # Each axis
    # Section via the operator: it keeps the far side, so the cut faces the viewer
    for axis, probe, look in (('X', (0, -32, 0), (80, 0, 70)), ('Y', (-32, 0, 0), (80, 0, -20)),
                              ('Y', (-32, 0, 0), (80, 0, 160))):
        settings(s, mode='OFF')
        view.look((0, 0, 0), 220, look)
        with view.override():
            bpy.ops.crosscut.section(axis=axis)
        yield from settle()
        shot = Shot(view, f"section_{axis.lower()}_from_{look[2]}")
        check(T, f"{axis}: cap visible from the cut side", is_green(shot.at(view.px(probe))),
              f"{shot.at(view.px(probe))}")
    check(T, "no draw errors", not errors(), str(errors()))


@test
def slices(view):
    T = "slices"
    scene = new_scene("cc-slice")
    hollow_sphere("part-001", 40, 25)
    s = scene.crosscut
    view.look((0, 0, 0), 220, (55, 0, 30))
    settings(s, mode='SLICE', orientation='Z', offset=0.0, thickness=0.0)
    yield 0.1
    yield from settle()
    shot = Shot(view, "slice_section_only")
    bg = bg_of(shot, view)
    check(T, "section only: annulus is cap colour", is_green(shot.at(view.px((0, -32, 0)))))
    check(T, "section only: hole is background", near(shot.at(view.px((0, 0, 0))), bg, BG_TOL),
          f"{shot.at(view.px((0, 0, 0)))}")
    check(T, "section only: bottom shell hidden", near(shot.at(view.px((0, 0, -39))), bg, BG_TOL))

    settings(s, mode='SLICE', orientation='Z', offset=0.0, thickness=10.0)
    yield from settle()
    shot = Shot(view, "slice_slab_10")
    check(T, "slab: top cap at z=+5", is_green(shot.at(view.px((0, -32, 5)))))
    check(T, "slab: outer wall between caps is shaded part",
          is_greyish(shot.at(view.px((0, -39.3, 0))), lo=60), f"{shot.at(view.px((0, -39.3, 0)))}")
    check(T, "slab: pole clipped", near(shot.at(view.px((0, 0, 39))), bg, BG_TOL))

    # Backfaces + a zero-thickness slice would show nothing at all: it shows the cut in backface red
    settings(s, mode='SLICE', orientation='Z', offset=0.0, thickness=0.0, cap_style='BACKFACES')
    yield from settle()
    shot = Shot(view, "slice_section_only_backfaces")
    c = shot.at(view.px((0, -32, 0)))
    check(T, "backfaces, zero thickness: section shown in backface red", is_red(c), f"{c}")
    check(T, "backfaces, zero thickness: hole is background", near(shot.at(view.px((0, 0, 0))), bg, BG_TOL))
    settings(s, mode='SLICE', orientation='Z', offset=0.0, thickness=10.0, cap_style='BACKFACES')
    yield from settle()
    shot = Shot(view, "slice_slab_backfaces")
    check(T, "backfaces, slab: no caps", not is_red(shot.at(view.px((0, -32, 5))))
          and not is_green(shot.at(view.px((0, -32, 5)))), f"{shot.at(view.px((0, -32, 5)))}")
    check(T, "no draw errors", not errors(), str(errors()))


@test
def multibody(view):
    T = "multibody"
    scene = new_scene("cc-multi")
    box("part-001", (40, 30, 30), (-12, 0, 0), (0.3, 0.55, 0.85))
    cylinder("part-002", 14, 50, (14, 0, 0), (0.9, 0.6, 0.2))
    box("part-003", (20, 20, 20), (45, 0, 0), (0.45, 0.75, 0.35))
    s = scene.crosscut
    view.look((12, 0, 0), 230, (35, 0, 15))
    settings(s, mode='SECTION', orientation='Z', offset=0.0, color_source='OBJECT', cap_style='SOLID')
    yield 0.1
    yield from settle()
    shot = Shot(view, "multibody_interference")
    c = shot.at(view.px((4, 0, 0)))  # inside both part-001 and part-002
    check(T, "overlap is red", is_red(c), f"{c}")
    c = shot.at(view.px((-25, 0, 0)))
    check(T, "part-001 alone is its colour (blue)", c[2] > c[0] + 40, f"{c}")
    c = shot.at(view.px((45, 0, 0)))
    check(T, "part-003 alone is its colour (green)", c[1] > c[0] + 20 and c[1] > c[2], f"{c}")

    settings(s, mode='SECTION', orientation='Z', offset=0.0, color_source='OBJECT', interference=False)
    yield from settle()
    shot = Shot(view, "multibody_no_interference")
    c = shot.at(view.px((4, 0, 0)))
    check(T, "interference off: overlap not red", not is_red(c), f"{c}")
    a1 = shot.at(view.px((-25, 0, 0)))   # part-001 alone (blue)
    a2 = shot.at(view.px((20, 0, 0)))    # part-002 alone (orange)
    # the overlap blends the two colours instead of one covering the other
    check(T, "interference off: overlap blends both colours",
          all(min(x, y) - 25 <= v <= max(x, y) + 25 for v, x, y in zip(c, a1, a2, strict=False))
          and not near(c, a1, 30) and not near(c, a2, 30), f"overlap {c} part-001 {a1} part-002 {a2}")

    # stripes: the overlap shows both parts' colours side by side
    settings(s, mode='SECTION', orientation='Z', offset=0.0, color_source='OBJECT', interference=False,
             overlap_style='STRIPES')
    yield from settle()
    shot = Shot(view, "multibody_stripes")
    cx, cy = view.px((4, 0, 0))
    patch = [tuple(p) for p in shot.px[cy + shot.oy - 12:cy + shot.oy + 12, cx + shot.ox - 12:cx + shot.ox + 12]
             .reshape(-1, 3)]
    blue = sum(p[2] > p[0] + 60 for p in patch)
    orange = sum(p[0] > p[2] + 60 for p in patch)
    check(T, "stripes: overlap has both colours", blue > 60 and orange > 60, f"blue {blue} orange {orange}")

    # interference appearance: solid, custom colour, half opacity over the stripes
    settings(s, mode='SECTION', orientation='Z', offset=0.0, color_source='OBJECT', interference=True,
             overlap_style='STRIPES', interference_style='SOLID', interference_color=(1.0, 0.0, 1.0),
             interference_opacity=1.0)
    yield from settle()
    shot = Shot(view, "multibody_interference_solid_magenta")
    c = shot.at(view.px((4, 0, 0)))
    check(T, "interference colour and style", c[0] > 200 and c[2] > 200 and c[1] < 60, f"{c}")
    settings(s, mode='SECTION', orientation='Z', offset=0.0, color_source='OBJECT', interference=True,
             overlap_style='STRIPES', interference_style='CROSS', interference_opacity=0.4)
    yield from settle()
    Shot(view, "multibody_interference_translucent")
    s.interference_color = (0.86, 0.10, 0.08)
    s.interference_opacity = 1.0
    s.overlap_style = 'BLEND'

    # Auto colours use the Cap Color only for white/grey parts: the panel hides it otherwise
    s.color_source = 'AUTO'
    with view.override():
        coloured = cc("draw").auto_uses_cap_color(bpy.context, s)
    check(T, "Auto, coloured parts: Cap Color not used (hidden)", not coloured)
    scene.objects["part-003"].color = (1, 1, 1, 1)
    with view.override():
        white = cc("draw").auto_uses_cap_color(bpy.context, s)
    check(T, "Auto, a white part: Cap Color used (shown)", white)
    scene.objects["part-003"].color = (0.45, 0.75, 0.35, 1)

    settings(s, mode='SECTION', orientation='Z', offset=0.0, color_source='OBJECT', cap_style='HATCH')
    yield from settle()
    Shot(view, "multibody_hatched")

    # Targets = Selected: only part-002 is capped, everything is still clipped
    for ob in scene.objects:
        ob.select_set(ob.name == "part-002")
    settings(s, mode='SECTION', orientation='Z', offset=0.0, targets='SELECTED', color_source='OBJECT')
    yield 0.05
    yield from settle()
    shot = Shot(view, "multibody_selected_only")
    c = shot.at(view.px((-25, 0, 0)))
    check(T, "selected-only: unselected part not capped (darker inside)", c[2] < 190, f"{c}")
    c = shot.at(view.px((20, 0, 0)))
    check(T, "selected-only: selected part capped", c[0] > c[2] + 40, f"{c}")
    check(T, "no draw errors", not errors(), str(errors()))


@test
def auto_colours(view):
    T = "auto_colours"
    scene = new_scene("cc-auto")
    box("part-001", (30, 30, 30), color=(1.0, 1.0, 1.0))
    s = scene.crosscut
    view.look((0, 0, 0), 160, (55, 0, 30))
    settings(s, mode='SECTION', orientation='Z', color_source='AUTO', cap_style='SOLID')
    yield 0.1
    yield from settle()
    shot = Shot(view, "auto_white_object")
    c = shot.at(view.px((-8, -8, 0)))
    side = shot.at(view.px((0, -15, -8)))
    check(T, "white object: cap stands out from the part", max(abs(a - b) for a, b in zip(c, side, strict=False)) > 40,
          f"cap {c} side {side}")


@test
def open_mesh(view):
    T = "open_mesh"
    scene = new_scene("cc-open")
    box("part-001", (30, 30, 30), open_top=True)
    s = scene.crosscut
    view.look((0, 0, 0), 160, (55, 0, 30))
    settings(s, mode='SECTION', orientation='X', offset=0.0)
    yield 0.1
    yield from settle()
    Shot(view, "open_mesh_closed_section")
    info = cc("draw").last_info(view.region)
    check(T, "X cut through the open top: flagged open", info.get("open") == ["part-001"], str(info.get("open")))
    settings(s, mode='SECTION', orientation='Z', offset=0.0)
    yield from settle()
    Shot(view, "open_mesh_z")
    info = cc("draw").last_info(view.region)
    check(T, "Z cut of open-top box is closed (no warning)", not info.get("open"), str(info.get("open")))
    # cut through a box with a deleted face along the cut plane: open contour
    settings(s, mode='SECTION', orientation='Y', offset=0.0, flip=True)  # keep the far half
    yield from settle()
    info = cc("draw").last_info(view.region)
    check(T, "Y cut crosses the hole: flagged open", info.get("open") == ["part-001"], str(info.get("open")))
    shot = Shot(view, "open_mesh_warning")
    c = shot.at(view.px((0, 0, 0)))
    check(T, "open contour is closed and filled", is_green(c), f"{c}")
    check(T, "no draw errors", not errors(), str(errors()))


@test
def native_altb(view):
    T = "native_altb"
    scene = new_scene("cc-native")
    hollow_sphere("part-001", 40, 25)
    s = scene.crosscut
    settings(s, mode='OFF', cap_style='SOLID')
    view.look((0, 0, 0), 220, (55, 0, 30))
    yield 0.1
    with view.override():
        w, h = view.region.width, view.region.height
        bpy.ops.view3d.clip_border(xmin=0, xmax=int(w * 0.5), ymin=0, ymax=h, wait_for_input=False)
    yield from settle()
    shot = Shot(view, "native_altb_box")
    bg = bg_of(shot, view)
    info = cc("draw").last_info(view.region)
    check(T, "native caps active", info.get("native"), str(info))
    cx, cy = view.px((0, 0, 0))
    c = shot.at((cx + 60, cy))
    check(T, "right half clipped", near(c, bg, BG_TOL), f"{c}")
    # Alt+B planes pass through the eye, so their caps are edge-on until you orbit
    view.look((0, 0, 0), 220, (55, 0, 75))
    yield from settle()
    shot = Shot(view, "native_altb_orbited")
    g = sum(is_green(tuple(p)) for p in shot.px[::8, ::8].reshape(-1, 3))
    check(T, "after orbiting, the box side cap shows", g > 200, f"{g} green samples")
    settings(s, mode='OFF', cap_style='BACKFACES')
    yield from settle()
    shot = Shot(view, "native_altb_backfaces")
    g = sum(is_green(tuple(p)) for p in shot.px[::8, ::8].reshape(-1, 3))
    check(T, "Backfaces: no Alt+B caps", g < 5, f"{g} green samples")

    # Outlines stay inside the box: a box over one quadrant cuts the sphere with
    # two side planes, and each side's contour runs on past the other side
    view.rv3d.use_clip_planes = False
    view.look((0, 0, 0), 220, (55, 0, 30))
    yield from settle()
    with view.override():
        w, h = view.region.width, view.region.height
        bpy.ops.view3d.clip_border(xmin=0, xmax=int(w * 0.5), ymin=0, ymax=int(h * 0.5), wait_for_input=False)
    view.look((0, 0, 0), 220, (75, 0, 70))
    settings(s, mode='OFF', cap_style='SOLID', outline=False)
    yield from settle()
    off = Shot(view, "native_altb_quadrant_no_outline")
    settings(s, mode='OFF', cap_style='SOLID', outline=True, outline_width=3.0)
    yield from settle()
    on = Shot(view, "native_altb_quadrant_outline")
    bg = bg_of(off, view)
    fg = np.abs(off.px - np.array(bg)).max(axis=2) > BG_TOL
    near_fg = fg.copy()
    for dx in range(-6, 7, 2):
        for dy in range(-6, 7, 2):
            near_fg |= np.roll(np.roll(fg, dy, 0), dx, 1)
    dark = on.px.max(axis=2) < 40
    stray = int((dark & ~near_fg).sum())
    check(T, "outlines clipped to the Alt+B box", stray < 50, f"{stray} dark pixels away from any part")
    view.rv3d.use_clip_planes = False
    yield from settle()
    check(T, "no draw errors", not errors(), str(errors()))


@test
def handoff(view):
    T = "handoff"
    scene = new_scene("cc-handoff")
    hollow_sphere("part-001", 40, 25)
    s = scene.crosscut
    view.look((0, 0, 0), 220, (55, 0, 30))
    settings(s, mode='OFF')
    yield 0.1

    # 1) No Alt+B box ever drawn: turning on works, turning off restores "no clipping"
    with view.override():
        bpy.ops.crosscut.toggle()
    yield 0.1
    yield from settle()
    check(T, "toggle on: clipping on", view.rv3d.use_clip_planes and s.mode != 'OFF', s.mode)
    with view.override():
        bpy.ops.crosscut.toggle()
    yield 0.1
    yield from settle()
    check(T, "toggle off: clipping restored to off", not view.rv3d.use_clip_planes and s.mode == 'OFF')

    # 2) An Alt+B box exists: Crosscut on replaces it, off restores it. Blender
    # shades the Alt+B box volume, which shows once you orbit; it must go too.
    view.look((0, 0, 0), 220, (55, 0, 75))
    yield from settle()
    plain = Shot(view, "handoff_plain")
    view.look((0, 0, 0), 220, (55, 0, 30))
    yield from settle()
    with view.override():
        w, h = view.region.width, view.region.height
        bpy.ops.view3d.clip_border(xmin=0, xmax=int(w * 0.5), ymin=0, ymax=h, wait_for_input=False)
    view.look((0, 0, 0), 220, (55, 0, 75))
    yield 0.05
    yield from settle()
    boxed = Shot(view, "handoff_altb_box")
    saved = [tuple(p) for p in view.rv3d.clip_planes]
    with view.override():
        bpy.ops.crosscut.set_mode(mode='SECTION')
    yield 0.1
    yield from settle()
    check(T, "on over Alt+B: ours", cc("draw").last_info(view.region).get("ours"))
    on = Shot(view, "handoff_section_over_altb")
    # compare against the unclipped view where it is background, away from the overlay texts
    bgc = np.array(bg_of(plain, view))
    empty = np.abs(plain.px - bgc).max(axis=2) == 0
    rw, rh = view.region.width, view.region.height
    win = np.zeros_like(empty)
    win[plain.oy + int(rh * 0.1):plain.oy + int(rh * 0.9), plain.ox + int(rw * 0.15):plain.ox + int(rw * 0.85)] = True

    def shaded(shot):
        return int((empty & win & (np.abs(shot.px - bgc).max(axis=2) > 0)).sum())
    check(T, "Alt+B box volume is shaded (test sees it)", shaded(boxed) > 2000, f"{shaded(boxed)} px")
    check(T, "on over Alt+B: no leftover box shading", shaded(on) < 200, f"{shaded(on)} px")
    with view.override():
        bpy.ops.crosscut.toggle()
    yield 0.1
    yield from settle()
    now = [tuple(p) for p in view.rv3d.clip_planes]
    check(T, "off: Alt+B box restored", view.rv3d.use_clip_planes and np.allclose(saved, now, atol=1e-4))
    view.rv3d.use_clip_planes = False

    # 3) User presses Alt+B while Crosscut is on: Crosscut hands back and turns off
    settings(s, mode='SECTION', orientation='Z')
    yield from settle()
    with view.override():
        bpy.ops.view3d.clip_border(xmin=0, xmax=int(view.region.width * 0.3), ymin=0,
                                   ymax=view.region.height, wait_for_input=False)
    yield from settle()
    yield 0.2
    yield from settle()
    check(T, "Alt+B while on: Crosscut turned off", s.mode == 'OFF', s.mode)
    check(T, "Alt+B while on: user's box kept", view.rv3d.use_clip_planes)
    view.rv3d.use_clip_planes = False

    # 4) Alt+B toggled off while Crosscut is on (use_clip_planes False)
    settings(s, mode='SECTION', orientation='Z')
    yield from settle()
    view.rv3d.use_clip_planes = False
    yield from settle()
    yield 0.2
    yield from settle()
    check(T, "clipping toggled off under us: Crosscut off", s.mode == 'OFF', s.mode)
    check(T, "no draw errors", not errors(), str(errors()))


@test
def operators(view):
    T = "operators"
    scene = new_scene("cc-ops")
    ob = hollow_sphere("part-001", 40, 25)
    s = scene.crosscut
    view.look((0, 0, 0), 220, (55, 0, 30))
    settings(s, mode='OFF')
    yield 0.1
    with view.override():
        bpy.ops.crosscut.section(axis='X')
    check(T, "section X: on, centred", s.mode == 'SECTION' and s.orientation == 'X' and abs(s.offset) < 1e-4,
          f"{s.mode} {s.orientation} {s.offset}")
    with view.override():
        bpy.ops.crosscut.step(direction=1)
    check(T, "step +1", abs(s.offset - s.step) < 1e-4, f"{s.offset}")
    with view.override():
        bpy.ops.crosscut.step(direction=-1, multiplier=10)
    check(T, "step -10", abs(s.offset + 9 * s.step) < 1e-5, f"{s.offset}")
    s.position = 1.0
    check(T, "scrub to 1 = max X", abs(s.offset - 40.0) < 0.5, f"{s.offset}")
    s.position = 0.25
    check(T, "scrub get/set round trip", abs(s.position - 0.25) < 1e-4, f"{s.position}")
    with view.override():
        bpy.ops.crosscut.center()
    check(T, "center", abs(s.offset) < 1e-4, f"{s.offset}")
    scene.cursor.location = (7, 8, 9)
    with view.override():
        bpy.ops.crosscut.to_cursor()
    check(T, "to cursor", abs(s.offset - 7) < 1e-4, f"{s.offset}")
    with view.override():
        bpy.ops.crosscut.toggle_slice()
    check(T, "toggle slice", s.mode == 'SLICE')
    with view.override():
        bpy.ops.crosscut.toggle_caps()
    check(T, "toggle caps -> backfaces", s.cap_style == 'BACKFACES')
    with view.override():
        bpy.ops.crosscut.toggle_caps()
    check(T, "toggle caps -> back", s.cap_style != 'BACKFACES')
    with view.override():
        bpy.ops.crosscut.flip()
    check(T, "flip", s.flip)
    s.flip = False
    for o in scene.objects:
        o.select_set(o == ob)
    bpy.context.view_layer.objects.active = ob
    with view.override():
        bpy.ops.crosscut.to_selection()
    check(T, "to selection", abs(s.offset) < 1e-4, f"{s.offset}")
    with view.override():
        bpy.ops.crosscut.add_plane(align='VIEW')
    check(T, "add plane: object orientation", s.orientation == 'OBJECT' and s.plane_object is not None)
    yield from settle()
    Shot(view, "ops_plane_from_view")
    pl = s.plane_object
    pl.rotation_euler = (math.radians(30), 0, 0)
    pl.location = (0, 0, 5)
    yield 0.05
    yield from settle()
    Shot(view, "ops_plane_object_tilted")
    check(T, "object plane: still ours", cc("draw").last_info(view.region).get("ours"))
    with view.override():
        bpy.ops.crosscut.use_bounds()
    check(T, "use bounds", s.range_source == 'OBJECT')
    s.range_source = 'TARGETS'
    s.range_object = None
    check(T, "no draw errors", not errors(), str(errors()))


@test
def modes_and_view_plane(view):
    T = "modes_and_view_plane"
    scene = new_scene("cc-modes")
    hollow_sphere("part-001", 40, 25, loc=(100, 0, 0))
    s = scene.crosscut
    check(T, "defaults: model-space hatch, 0.5 spacing",
          s.hatch_space == 'MODEL' and abs(s.hatch_pitch - 0.5) < 1e-6, f"{s.hatch_space} {s.hatch_pitch}")
    s.color_source, s.single_color, s.cap_style = 'SINGLE', GREEN, 'SOLID'
    view.look((100, 0, 0), 220, (55, 0, 30))
    yield 0.1
    # first use starts in the middle of the range (part is centred at x=100)
    s.orientation = 'X'
    with view.override():
        bpy.ops.crosscut.set_mode(mode='SECTION')
    check(T, "Section button: on, scrub 0.5", s.mode == 'SECTION' and abs(s.position - 0.5) < 1e-3,
          f"{s.mode} {s.position}")
    s.position = 0.3
    with view.override():
        bpy.ops.crosscut.set_mode(mode='SLICE')
    check(T, "Slice button: switches mode, keeps position", s.mode == 'SLICE' and abs(s.position - 0.3) < 1e-3)
    with view.override():
        bpy.ops.crosscut.set_mode(mode='SLICE')
    check(T, "Slice again: off", s.mode == 'OFF')
    with view.override():
        bpy.ops.crosscut.set_mode(mode='SECTION')
    check(T, "on again: position kept", s.mode == 'SECTION' and abs(s.position - 0.3) < 1e-3, f"{s.position}")
    s.orientation = 'Y'
    check(T, "axis change re-centres", abs(s.position - 0.5) < 1e-3, f"{s.position}")

    # View plane: faces the view, stays put when orbiting
    view.look((100, 0, 0), 220, (60, 0, 40))
    yield from settle()
    with view.override():
        bpy.ops.crosscut.from_view()
    vz = view.rv3d.view_rotation @ Vector((0, 0, 1))
    n = Vector(s.view_normal)
    check(T, "View: plane faces the view", s.orientation == 'VIEW' and n.dot(vz) > 0.999, f"{n} {vz}")
    check(T, "View: through the middle", abs(s.position - 0.5) < 1e-3 and not s.flip, f"{s.position} {s.flip}")
    yield from settle()
    shot = Shot(view, "view_plane")
    c = shot.at(view.px(Vector((100, 0, 0)) + n.orthogonal().normalized() * 32))  # in the cut ring
    check(T, "View: looking straight at the cut", is_green(c), f"{c}")
    view.look((100, 0, 0), 220, (60, 0, 90))
    yield from settle()
    check(T, "View: orbiting does not move the plane", Vector(s.view_normal).dot(n) > 0.9999)
    Shot(view, "view_plane_orbited")
    with view.override():
        bpy.ops.crosscut.step(direction=1)
    check(T, "View: step moves along the normal", abs(engine_coord(s) - (n.dot(Vector((100, 0, 0))) + s.step)) < 1e-3,
          f"{engine_coord(s)}")
    s.scrub_distance = True
    check(T, "scrub by distance: offset is the position", abs(s.offset - s.step) < 1e-4, f"{s.offset}")
    s.scrub_distance = False

    # plane tint: inside the frame but off the part is tinted, not background
    settings(s, mode='SECTION', orientation='Z', offset=0.0, plane_display='NONE')
    view.look((100, 0, 0), 220, (55, 0, 30))
    yield from settle()
    plain = Shot(view, "plane_none")
    p = view.px((100 + 41, 41, 0))
    settings(s, mode='SECTION', orientation='Z', offset=0.0, plane_display='TINT')
    yield from settle()
    tint = Shot(view, "plane_tint")
    check(T, "Tint: plane corner is tinted", not near(tint.at(p), plain.at(p), 4), f"{tint.at(p)} vs {plain.at(p)}")
    check(T, "Tint: cap still its colour", is_green(tint.at(view.px((100, -32, 0)))))
    settings(s, mode='SECTION', orientation='Z', offset=0.0, plane_display='HATCH')
    yield from settle()
    Shot(view, "plane_hatch")
    check(T, "no draw errors", not errors(), str(errors()))


def engine_coord(s):
    return cc("engine").plane_coordinate(s)


@test
def live_updates(view):
    T = "live_updates"
    scene = new_scene("cc-live")
    ob = box("part-001", (30, 30, 30))
    s = scene.crosscut
    view.look((0, 0, 0), 160, (55, 0, 30))
    settings(s, mode='SECTION', orientation='Z', offset=0.0)
    yield 0.1
    yield from settle()
    shot = Shot(view, "live_before")
    p_out = (0, -20, 0)  # outside the 30 mm box, inside once it's scaled up
    check(T, "before: probe outside the cap", not is_green(shot.at(view.px(p_out))))

    # object transform
    ob.scale = (1.6, 1.6, 1.0)
    yield 0.1
    yield from settle()
    shot = Shot(view, "live_scaled")
    check(T, "object scale updates the cap", is_green(shot.at(view.px(p_out))), f"{shot.at(view.px(p_out))}")
    ob.scale = (1, 1, 1)

    # edit mode: move vertices, the section follows
    bpy.context.view_layer.objects.active = ob
    for o in scene.objects:
        o.select_set(o == ob)
    with view.override():
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.transform.resize(value=(1.6, 1.6, 1.0))
    yield 0.1
    yield from settle()
    shot = Shot(view, "live_editmode")
    check(T, "edit mode edit updates the cap", is_green(shot.at(view.px(p_out))), f"{shot.at(view.px(p_out))}")
    with view.override():
        bpy.ops.object.mode_set(mode='OBJECT')
    yield 0.05

    # undo restores
    bpy.ops.ed.undo_push(message="cc test")
    ob.data.vertices[0].co.x += 0.0  # no-op
    yield from settle()

    # modifiers: an array modifier adds a second copy at +40 x
    with view.override():
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.transform.resize(value=(1 / 1.6, 1 / 1.6, 1.0))
        bpy.ops.object.mode_set(mode='OBJECT')
    mod = ob.modifiers.new("Array", 'ARRAY')
    mod.relative_offset_displace = (1.5, 0, 0)
    view.look((22, 0, 0), 200, (55, 0, 30))
    yield 0.1
    yield from settle()
    shot = Shot(view, "live_array_modifier")
    check(T, "array modifier copy is capped", is_green(shot.at(view.px((45, 0, 0)))), f"{shot.at(view.px((45, 0, 0)))}")

    # instances: a collection instance of the box
    coll = bpy.data.collections.new("inst-src")
    scene.collection.children.link(coll)
    src = box("part-002", (10, 10, 10), color=(0.8, 0.8, 0.8))
    scene.collection.objects.unlink(src)
    coll.objects.link(src)
    coll.hide_viewport = False
    vl_coll = bpy.context.view_layer.layer_collection.children[coll.name]
    vl_coll.exclude = True
    inst = bpy.data.objects.new("inst-001", None)
    inst.instance_type = 'COLLECTION'
    inst.instance_collection = coll
    inst.location = (0, 35, 0)
    scene.collection.objects.link(inst)
    view.look((10, 15, 0), 220, (55, 0, 30))
    yield 0.1
    yield from settle()
    shot = Shot(view, "live_instance")
    check(T, "collection instance is capped", is_green(shot.at(view.px((0, 35, 0)))), f"{shot.at(view.px((0, 35, 0)))}")
    check(T, "no draw errors", not errors(), str(errors()))


@test
def quad_view(view):
    T = "quad_view"
    scene = new_scene("cc-quad")
    hollow_sphere("part-001", 40, 25)
    s = scene.crosscut
    settings(s, mode='SECTION', orientation='Z')
    with view.override():
        bpy.ops.screen.region_quadview()
    yield 0.2
    yield from settle()
    Shot(view, "quad_view")
    check(T, "no draw errors", not errors(), str(errors()))
    with view.override():
        bpy.ops.screen.region_quadview()
    yield 0.2
    view.region = next(r for r in view.area.regions if r.type == 'WINDOW')


@test
def readout(view):
    T = "readout"
    scene = new_scene("cc-readout")
    hollow_sphere("part-001", 40, 25)
    vol = box("bucket-01", (120, 120, 120), color=(0.5, 0.5, 0.5))
    vol.display_type = 'WIRE'
    s = scene.crosscut
    settings(s, mode='SECTION', orientation='Z', offset=12.0, plane_display='FRAME', range_source='OBJECT',
             range_object=vol, step=0.08, color_source='AUTO', cap_style='HATCH')
    view.look((0, 0, 0), 330, (60, 0, 30))
    yield 0.1
    yield from settle()
    Shot(view, "readout_range_object")
    text = cc("draw").readout_lines(scene, s, cc("draw").last_info(view.region))[0][0]
    check(T, "readout in scene units (mm)", "12" in text and "mm" in text, repr(text))
    check(T, "no draw errors", not errors(), str(errors()))


@test
def shading_modes(view):
    T = "shading_modes"
    scene = new_scene("cc-shading")
    hollow_sphere("part-001", 40, 25)
    s = scene.crosscut
    view.look((0, 0, 0), 220, (55, 0, 30))
    settings(s, mode='SECTION', orientation='Z')
    for st in ('WIREFRAME', 'MATERIAL'):
        view.space.shading.type = st
        yield 0.3
        yield from settle()
        Shot(view, f"shading_{st.lower()}")
    view.space.shading.type = 'SOLID'
    view.space.shading.show_xray = True
    yield from settle()
    Shot(view, "shading_xray")
    view.space.shading.show_xray = False
    check(T, "no draw errors", not errors(), str(errors()))


@test
def performance(view):
    T = "performance"
    scene = new_scene("cc-perf")
    dense_sphere("part-001", 8)  # ~1.3 M triangles
    s = scene.crosscut
    view.look((0, 0, 0), 160, (55, 0, 30))
    settings(s, mode='SECTION', orientation='Z', cap_style='HATCH')
    yield 0.1
    t0 = time.perf_counter()
    redraw(1)
    first = time.perf_counter() - t0
    times = []
    for i in range(20):
        s.offset = -25 + i * 2.5
        t0 = time.perf_counter()
        redraw(1)
        times.append(time.perf_counter() - t0)
    med = sorted(times)[len(times) // 2]
    Shot(view, "perf_dense")
    check(T, f"scrub frame time on 1.3M tris (first {first * 1000:.0f} ms, median {med * 1000:.0f} ms)",
          med < 0.25)
    check(T, "no draw errors", not errors(), str(errors()))


@test
def drag_perf(view):
    """Moving a part must stay smooth with Alt+B clipping too (6 cap planes, not 1)."""
    T = "drag_perf"
    scene = new_scene("cc-drag")
    ob = dense_sphere("part-001", 7)
    dense_sphere("part-002", 7).location = (60, 0, 0)
    s = scene.crosscut
    view.look((30, 0, 0), 260, (55, 0, 30))
    settings(s, mode='SECTION', orientation='Z', cap_style='HATCH')

    def drag_ms():
        times = []
        for i in range(16):
            ob.location.x = i * 0.5
            t0 = time.perf_counter()
            bpy.context.view_layer.update()
            redraw(1)
            times.append(time.perf_counter() - t0)
        return sorted(times)[len(times) // 2] * 1000

    yield 0.1
    redraw(1)
    sec = drag_ms()
    settings(s, mode='OFF', cap_style='HATCH')
    yield from settle()
    with view.override():
        w, h = view.region.width, view.region.height
        bpy.ops.view3d.clip_border(xmin=int(w * 0.42), xmax=int(w * 0.58), ymin=int(h * 0.4),
                                   ymax=int(h * 0.6), wait_for_input=False)
    yield from settle()
    nat = drag_ms()
    view.look((30, 0, 0), 260, (55, 0, 60))   # orbit: the box sides are no longer edge-on
    yield from settle()
    orb = drag_ms()
    Shot(view, "drag_altb_orbited")
    print(f"    drag frame: section {sec:.0f} ms, Alt+B {nat:.0f} ms, Alt+B orbited {orb:.0f} ms")
    check(T, f"Alt+B drag frame {nat:.0f} ms (section {sec:.0f} ms)", nat < max(2.0 * sec, 40))
    check(T, f"Alt+B orbited drag frame {orb:.0f} ms", orb < max(3.0 * sec, 60))
    view.rv3d.use_clip_planes = False
    yield from settle()
    check(T, "no draw errors", not errors(), str(errors()))


@test
def ui_panels(view):
    T = "ui_panels"
    scene = new_scene("cc-ui")
    hollow_sphere("part-001", 40, 25)
    vol = box("bucket-01", (120, 120, 120), color=(0.5, 0.5, 0.5))
    vol.display_type = 'WIRE'
    s = scene.crosscut
    view.look((0, 0, 0), 300, (55, 0, 30))
    settings(s, mode='SECTION', orientation='Z', cap_style='HATCH', color_source='AUTO',
             range_source='OBJECT', range_object=vol)
    view.space.show_region_ui = True
    ui = next(r for r in view.area.regions if r.type == 'UI')
    # The active sidebar tab is read-only from Python: show our panels in the
    # active "Tool" tab for the screenshot, then put them back.
    panels = [c for c in cc("ui").classes if getattr(c, "bl_region_type", "") == 'UI']
    for c in reversed(panels):
        bpy.utils.unregister_class(c)
    for c in panels:
        c.bl_category = "Tool"
        bpy.utils.register_class(c)
    yield 0.2
    yield from settle()
    shot = Shot(view, "ui_sidebar")
    # crop the sidebar out of the area screenshot
    x0 = ui.x - view.area.x
    os.makedirs(OUT, exist_ok=True)
    try:
        import subprocess
        subprocess.run(["convert", shot.path, "-crop", f"{ui.width}x{view.area.height}+{x0}+0",
                        os.path.join(OUT, "ui_sidebar_crop.png")], check=False)
    except OSError:
        pass
    view.space.show_region_ui = False
    for c in reversed(panels):
        bpy.utils.unregister_class(c)
    for c in panels:
        c.bl_category = "Crosscut"
        bpy.utils.register_class(c)
    with view.override():
        bpy.ops.wm.call_panel(name="CROSSCUT_PT_popover", keep_open=True)
    yield 0.2
    yield from settle()
    Shot(view, "ui_popover")
    check(T, "no draw errors", not errors(), str(errors()))


@test
def zz_pie(view):
    # last: an open pie menu (or the popover above) would swallow the following tests' events
    T = "pie"
    scene = new_scene("cc-pie")
    hollow_sphere("part-001", 40, 25)
    view.look((0, 0, 0), 220, (55, 0, 30))
    settings(scene.crosscut, mode='SECTION', orientation='Z', cap_style='HATCH', color_source='AUTO')
    with view.override():
        bpy.ops.wm.call_menu_pie(name="CROSSCUT_MT_pie")
    yield 0.2
    yield from settle()
    Shot(view, "pie_menu")
    check(T, "no draw errors", not errors(), str(errors()))


# --------------------------------------------------------------------- runner

def _runner():
    view = None
    try:
        if not hasattr(bpy.types.Scene, "crosscut"):
            bpy.ops.preferences.addon_enable(module=MODULE)
        view = View()
        with view.override():
            bpy.ops.screen.screen_full_area()
        yield 0.3
        view = View()
        print(f"Crosscut viewport tests: Blender {bpy.app.version_string}, "
              f"GPU backend {gpu.platform.backend_type_get()}, region "
              f"{view.region.width}x{view.region.height}, out {OUT}")
        for fn in TESTS:
            if ONLY and ONLY not in fn.__name__:
                continue
            print(f"- {fn.__name__}")
            setup_view(view)
            try:
                yield from fn(view)
            except Exception:
                traceback.print_exc()
                check(fn.__name__, "ran without exception", False, traceback.format_exc().splitlines()[-1])
            bpy.context.scene.crosscut.mode = 'OFF'
            yield 0.05
            view.rv3d.use_clip_planes = False
            yield 0.05
    except Exception:
        traceback.print_exc()
        check("runner", "setup", False)
    finally:
        _finish()


def _finish():
    fails = [r for r in results if not r[2]]
    print(f"\nCrosscut viewport tests: {len(results) - len(fails)} passed, {len(fails)} failed")
    for t, name, _ok, detail in fails:
        print(f"  FAIL {t}: {name} {detail}")
    print("Screenshots:", OUT)
    if KEEP:
        return
    sys.stdout.flush()
    os._exit(1 if fails or not results else 0)


_gen = None


def _tick():
    global _gen
    if _gen is None:
        _gen = _runner()
    try:
        delay = next(_gen)
    except StopIteration:
        return None
    return float(delay or 0.01)


bpy.app.timers.register(_tick, first_interval=1.0)
