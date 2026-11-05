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
                hatch_vary=True, outline=True, plane_display='NONE',
                show_readout=True, range_source='TARGETS', range_object=None,
                hatch_space='SCREEN', hatch_pitch_px=10.0, scrub_distance=False, overlap_style='HIGHLIGHT',
                interference_style='CROSS', interference_opacity=1.0, plane_opacity=0.10,
                stripe_width_px=12.0, open_opacity=1.0, object_axis='Z', clip_tint=True,
                measure_max=True, measure_local=True, measure_section_max=False,
                measure_ignore_overlaps=False, measure_keep=False, fill_saturation=1.0, fill_brightness=1.0, fill_tint_amount=0.0,
                fill_opacity=1.0)
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

    settings(s, mode='SECTION', orientation='Z', offset=0.0, color_source='OBJECT', overlap_style='BLEND')
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
    settings(s, mode='SECTION', orientation='Z', offset=0.0, color_source='OBJECT', overlap_style='STRIPES')
    yield from settle()
    shot = Shot(view, "multibody_stripes")
    cx, cy = view.px((4, 0, 0))
    patch = [tuple(p) for p in shot.px[cy + shot.oy - 12:cy + shot.oy + 12, cx + shot.ox - 12:cx + shot.ox + 12]
             .reshape(-1, 3)]
    blue = sum(p[2] > p[0] + 60 for p in patch)
    orange = sum(p[0] > p[2] + 60 for p in patch)
    check(T, "stripes: overlap has both colours", blue > 60 and orange > 60, f"blue {blue} orange {orange}")

    # interference appearance: solid, custom colour, half opacity over the stripes
    settings(s, mode='SECTION', orientation='Z', offset=0.0, color_source='OBJECT', overlap_style='HIGHLIGHT', interference_style='SOLID', interference_color=(1.0, 0.0, 1.0),
             interference_opacity=1.0)
    yield from settle()
    shot = Shot(view, "multibody_interference_solid_magenta")
    c = shot.at(view.px((4, 0, 0)))
    check(T, "interference colour and style", c[0] > 200 and c[2] > 200 and c[1] < 60, f"{c}")
    settings(s, mode='SECTION', orientation='Z', offset=0.0, color_source='OBJECT', overlap_style='HIGHLIGHT', interference_style='CROSS', interference_opacity=0.4)
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
def coplanar_clash(view):
    # overlapping caps lie in one plane: they must not z-fight with each other or
    # with the interference fill, at any distance or angle
    T = "coplanar_clash"
    scene = new_scene("cc-clash")
    box("part-001", (60, 40, 30), (-10, 0, 0), (0.1, 0.1, 0.9))
    box("part-002", (60, 37, 34), (10, 2, 0), (0.9, 0.1, 0.1))
    s = scene.crosscut
    view.space.clip_start = 0.01
    view.space.clip_end = 1000000.0

    def spread(shot):
        # overlap region only: flat fills must give one colour
        pts = [view.px((x, y, 0)) for x in np.linspace(-13, 13, 25) for y in np.linspace(-12, 12, 25)]
        cols = np.array([shot.at(p, r=0) for p in pts if p])
        return int(np.ptp(cols, axis=0).max())

    for dist, rot in ((900, (70, 0, 25)), (1500, (65, 0, 40)), (150, (60, 0, 10))):
        view.look((0, 0, 0), dist, rot)
        settings(s, mode='SECTION', orientation='Z', color_source='OBJECT', overlap_style='BLEND', outline=False)
        yield 0.05
        yield from settle()
        d = spread(Shot(view, f"clash_blend_{dist}"))
        check(T, f"blend overlap is flat at {dist}", d <= 3, f"spread {d}")
        settings(s, mode='SECTION', orientation='Z', color_source='OBJECT', interference_style='SOLID', outline=False)
        yield from settle()
        d = spread(Shot(view, f"clash_interference_{dist}"))
        check(T, f"interference overlap is flat at {dist}", d <= 3, f"spread {d}")
    check(T, "no draw errors", not errors(), str(errors()))


@test
def selected_over_contour(view):
    # a selected part's contour must win over a neighbour's dark one where they coincide
    T = "selected_over_contour"
    scene = new_scene("cc-seloutline")
    a = box("part-001", (30, 30, 30), (-15, 0, 0), (0.6, 0.6, 0.6))
    b = box("part-002", (30, 30, 30), (15, 0, 0), (0.6, 0.6, 0.6))
    s = scene.crosscut
    view.look((0, 0, 0), 160, (0, 0, 0))
    bpy.context.view_layer.update()
    sel = tuple(int(255 * v) for v in bpy.context.preferences.themes[0].view_3d.object_selected)
    for name, ob_sel in (("left", a), ("right", b)):
        for o in scene.objects:
            o.select_set(o == ob_sel)
        bpy.context.view_layer.objects.active = None
        settings(s, mode='SECTION', orientation='Z', flip=False)
        yield 0.05
        yield from settle()
        shot = Shot(view, f"selected_over_contour_{name}")
        # the shared wall at x=0, seen from above
        x, y = view.px((0, 5, 0))
        cols = [shot.at((x + dx, y), r=0) for dx in range(-2, 3)]
        check(T, f"shared wall shows the selection colour ({name} selected)",
              any(near(c, sel, 70) for c in cols), f"{cols} vs {sel}")
    # same profile stacked: the selected part below is only seen as Blender's outline
    for o in list(scene.objects):
        bpy.data.objects.remove(o)
    low = box("part-001", (30, 30, 30), (0, 0, -15), (0.6, 0.6, 0.6))
    box("part-002", (30, 30, 30), (0, 0, 15), (0.6, 0.6, 0.6))
    low.select_set(True)
    bpy.context.view_layer.objects.active = None
    view.look((0, 0, 0), 160, (40, 0, 30))
    settings(s, mode='SECTION', orientation='Z', offset=15.0)
    yield 0.05
    yield from settle()
    Shot(view, "selected_over_contour_stacked")
    # the plane on the interface: looking at it, the selected part's silhouette lies on the contour
    view.look((0, 0, 0), 160, (40, 0, 30))
    settings(s, mode='SECTION', orientation='Z', offset=0.0)
    yield from settle()
    shot = Shot(view, "selected_over_contour_interface")
    x, y = view.px((-15, 0, 0))
    cols = [shot.at((x + dx, y), r=0) for dx in range(-4, 5)]
    check(T, "plane on the interface: selected outline over the neighbour's contour",
          any(near(c, sel, 70) for c in cols), str(cols))
    # the flat face lying on the plane mustn't z-fight with the cap on it
    pts = [view.px((a, b, 0)) for a in np.linspace(-13, 13, 20) for b in np.linspace(-13, 13, 20)]
    d = int(np.ptp(np.array([shot.at(p, r=0) for p in pts]), axis=0).max())
    check(T, "cap on a flush face is flat", d <= 3, f"spread {d}")
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
    lines, warn, severe = cc("draw").readout_lines(scene, s, info)
    check(T, "open section: severe warning", len(severe) == 1 and not warn, f"{warn} {severe}")
    # a cut away from the hole: closed contour, but the mesh is open
    settings(s, mode='SECTION', orientation='Z', offset=0.0)
    yield from settle()
    info = cc("draw").last_info(view.region)
    lines, warn, severe = cc("draw").readout_lines(scene, s, info)
    check(T, "cut away from the hole: mild warning", info.get("open_mesh") == ["part-001"] and warn and not severe,
          f"{info.get('open_mesh')} {warn} {severe}")
    p = view.px((0, 0, 0))
    solid = Shot(view, "open_mesh_opacity_1").at(p)
    s.open_opacity = 0.5
    yield from settle()
    half = Shot(view, "open_mesh_opacity_half").at(p)
    check(T, "open part's cap is translucent", is_green(solid) and not near(half, solid, 25), f"{solid} {half}")
    # a closed part is not flagged
    scene.objects["part-001"].hide_set(True)
    closed = box("part-002", (30, 30, 30), (0, 0, 0))
    closed.select_set(False)
    yield 0.05
    yield from settle()
    info = cc("draw").last_info(view.region)
    check(T, "closed part: no warnings", not info.get("open") and not info.get("open_mesh"), str(info))
    c = Shot(view, "open_mesh_closed_part").at(p)
    check(T, "closed part's cap is opaque", near(c, solid, 8), f"{c} {solid}")
    check(T, "no draw errors", not errors(), str(errors()))


@test
def hatch_stays_put(view):
    # hiding a part must not change the others' hatch variation
    T = "hatch_stays_put"
    scene = new_scene("cc-hatchid")
    obs = [box(f"part-{i:03}", (10, 10, 10), (i * 15, 0, 0)) for i in range(1, 5)]
    s = scene.crosscut
    view.look((35, 0, 0), 120, (30, 0, 10))
    settings(s, mode='SECTION', orientation='Z', cap_style='HATCH')
    yield 0.05
    yield from settle()
    ref = Shot(view, "hatch_all")
    p = view.px((60, 0, 0))

    def patch(shot):
        x, y = p[0] + shot.ox, p[1] + shot.oy
        return shot.px[y - 25:y + 25, x - 25:x + 25].copy()

    before = patch(ref)
    obs[0].hide_set(True)
    yield 0.05
    yield from settle()
    hidden = patch(Shot(view, "hatch_one_hidden"))
    check(T, "hiding part-001 leaves part-004's hatch alone", int(np.abs(hidden - before).max()) <= 3,
          f"max diff {int(np.abs(hidden - before).max())}")
    obs[0].hide_set(False)
    box("part-000", (10, 10, 10), (0, 0, 0))
    yield 0.05
    yield from settle()
    added = patch(Shot(view, "hatch_one_added"))
    check(T, "a new part leaves part-004's hatch alone", int(np.abs(added - before).max()) <= 3,
          f"max diff {int(np.abs(added - before).max())}")
    check(T, "no draw errors", not errors(), str(errors()))


@test
def local_axes(view):
    T = "local_axes"
    scene = new_scene("cc-local")
    ob = box("part-001", (40, 40, 10), (5, 0, 0))
    box("part-002", (5, 5, 5), (60, 0, 0))
    ob.rotation_euler = (0, math.radians(30), 0)
    bpy.context.view_layer.update()
    for o in scene.objects:
        o.select_set(o == ob)
    bpy.context.view_layer.objects.active = ob
    s = scene.crosscut
    view.look((0, 0, 0), 200, (60, 0, 30))
    settings(s, mode='SECTION', orientation='X')
    s.plane_object = None
    s.orientation = 'OBJECT'
    check(T, "Object picks the selected part", s.plane_object == ob, str(s.plane_object))
    m = np.array(ob.matrix_world)
    for axis, i in (('X', 0), ('Y', 1), ('Z', 2)):
        s.object_axis = axis
        f = cc("engine").plane_frame(s)
        check(T, f"normal is local {axis}", np.allclose(f[0], m[:3, i] / np.linalg.norm(m[:3, i])), str(f[0]))
    yield 0.05
    yield from settle()
    Shot(view, "local_axis_z")
    s.object_axis = 'X'
    s.offset = 0.0
    yield from settle()
    Shot(view, "local_axis_x")
    info = cc("draw").last_info(view.region)
    head = cc("draw").readout_lines(scene, s, info)[0][0]
    check(T, "readout names the axis", "part-001 X" in head, repr(head))
    with view.override():
        before = ob.matrix_world.copy()
        bpy.ops.crosscut.add_plane(align='VIEW')
    check(T, "+ makes an Empty instead of moving the part",
          s.plane_object != ob and s.plane_object.type == 'EMPTY' and ob.matrix_world == before)
    check(T, "no draw errors", not errors(), str(errors()))


@test
def xray_caps(view):
    T = "xray_caps"
    scene = new_scene("cc-xray")
    box("part-001", (30, 30, 30))
    s = scene.crosscut
    view.look((0, 0, 0), 160, (60, 0, 30))
    settings(s, mode='SECTION', orientation='Z')
    yield 0.05
    yield from settle()
    p = view.px((0, 0, 0))
    solid = Shot(view, "xray_off").at(p)
    view.space.shading.show_xray = True
    view.space.shading.xray_alpha = 0.5
    yield from settle()
    xr = Shot(view, "xray_on").at(p)
    check(T, "X-ray: cap is translucent", is_green(solid) and xr[1] < solid[1] - 30, f"{solid} {xr}")
    view.space.shading.show_xray = False
    check(T, "no draw errors", not errors(), str(errors()))


@test
def clip_button_follows_key(view):
    # the sidebar's Clip button lights and unlights with Alt+B on the keyboard, with no hovering
    T = "clip_button_follows_key"
    if not bpy.app.use_event_simulate:
        print("    skipped: run Blender with --enable-event-simulate")
        return
    scene = new_scene("cc-clip-key")
    box("part-001", (30, 30, 30))
    s = scene.crosscut
    view.look((0, 0, 0), 160, (60, 0, 30))
    settings(s, cap_style='SOLID')
    view.space.show_region_ui = True
    ui = next(r for r in view.area.regions if r.type == 'UI')
    panels = [c for c in cc("ui").classes if getattr(c, "bl_region_type", "") == 'UI']
    for c in reversed(panels):
        bpy.utils.unregister_class(c)
    for c in panels:
        c.bl_category = "Tool"
        bpy.utils.register_class(c)
    yield 0.3
    win = bpy.context.window
    r = view.region
    cx, cy = r.x + r.width // 3, r.y + r.height // 2
    win.event_simulate('MOUSEMOVE', 'NOTHING', x=cx, y=cy)
    yield 0.5

    def blue(name):
        shot = Shot(view, name)
        x0 = ui.x - view.area.x
        p = shot.px[:, x0:x0 + ui.width]
        return int(np.count_nonzero((p[:, :, 2] > p[:, :, 0] + 60) & (p[:, :, 2] > 120)))

    off = blue("clip_key_before")
    # draw a box with the key
    win.event_simulate('B', 'PRESS', alt=True, x=cx, y=cy)
    win.event_simulate('B', 'RELEASE', alt=True, x=cx, y=cy)
    yield 0.2
    a, b = view.px((-12, -12, 15)), view.px((12, 12, 15))
    x0, x1 = sorted((a[0], b[0]))
    y0, y1 = sorted((a[1], b[1]))
    win.event_simulate('MOUSEMOVE', 'NOTHING', x=r.x + x0, y=r.y + y0)
    yield 0.05
    win.event_simulate('LEFTMOUSE', 'PRESS', x=r.x + x0, y=r.y + y0)
    yield 0.05
    win.event_simulate('MOUSEMOVE', 'NOTHING', x=r.x + x1, y=r.y + y1)
    yield 0.05
    win.event_simulate('LEFTMOUSE', 'RELEASE', x=r.x + x1, y=r.y + y1)
    yield 0.6
    check(T, "key drew a box", view.rv3d.use_clip_planes)
    on = blue("clip_key_box")
    check(T, "button lit by the key", on > off + 100, f"{on} vs {off}")
    win.event_simulate('MOUSEMOVE', 'NOTHING', x=cx, y=cy)
    win.event_simulate('B', 'PRESS', alt=True, x=cx, y=cy)
    win.event_simulate('B', 'RELEASE', alt=True, x=cx, y=cy)
    yield 0.6
    check(T, "key removed the box", not view.rv3d.use_clip_planes)
    now = blue("clip_key_after")
    check(T, "button unlit by the key", now <= off + 20, f"{now} vs {off}")
    view.space.show_region_ui = False
    for c in reversed(panels):
        bpy.utils.unregister_class(c)
    for c in panels:
        c.bl_category = "Crosscut"
        bpy.utils.register_class(c)
    check(T, "no draw errors", not errors(), str(errors()))


@test
def overlapping_shells(view):
    # two overlapping closed shells in one object stay filled; reversed shells still cut holes
    T = "overlapping_shells"
    scene = new_scene("cc-shells")
    bm = bmesh.new()
    for x in (-10, 10):
        made = bmesh.ops.create_cube(bm, size=1.0)
        bmesh.ops.scale(bm, vec=Vector((40, 30, 30)), verts=made["verts"])
        bmesh.ops.translate(bm, vec=Vector((x, 0, 0)), verts=made["verts"])
    me = bpy.data.meshes.new("part-001")
    bm.to_mesh(me)
    bm.free()
    ob = _link("part-001", me)
    s = scene.crosscut
    view.look((0, 0, 0), 200, (0, 0, 0))
    settings(s, mode='SECTION', orientation='Z')
    yield 0.05
    yield from settle()
    shot = Shot(view, "shells_overlap")
    c = shot.at(view.px((0, 0, 0)))
    check(T, "overlap inside one object is filled", is_green(c), f"{c}")
    c = shot.at(view.px((-25, 0, 0)))
    check(T, "the rest is filled", is_green(c), f"{c}")
    info = cc("draw").last_info(view.region)
    check(T, "no open warning", not info.get("open") and not info.get("open_mesh"), str(info))
    # selecting by section follows the same fill
    settings(s, mode='SLICE', orientation='Z', thickness=0.0)
    planes = cc("engine").compute_planes(s)
    hit = cc("engine").objects_at(bpy.context, s, np.array((0.0, 0.0, 0.0)), np.asarray(planes[1][0][0]),
                                  bpy.context.evaluated_depsgraph_get())
    check(T, "clicking the overlap finds the part", hit == [ob], str(hit))
    # flipped normals on one face: not trustworthy, so it falls back to even-odd
    ob.data.polygons[0].flip()
    ob.data.update()
    settings(s, mode='SECTION', orientation='Z')
    yield 0.1
    yield from settle()
    shot = Shot(view, "shells_inconsistent")
    c = shot.at(view.px((0, 0, 0)))
    check(T, "inconsistent normals: even-odd, overlap is a hole", not is_green(c), f"{c}")
    c = shot.at(view.px((-25, 0, 0)))
    check(T, "inconsistent normals: no streaks in the fill", is_green(c), f"{c}")
    check(T, "no draw errors", not errors(), str(errors()))


@test
def axis_buttons_start_section(view):
    T = "axis_buttons_start_section"
    scene = new_scene("cc-axis-off")
    box("part-001", (30, 30, 30))
    s = scene.crosscut
    view.look((0, 0, 0), 160, (60, 0, 30))
    settings(s, mode='OFF', orientation='Z')
    s.last_mode = 'SECTION'
    yield 0.05
    with view.override():
        bpy.ops.crosscut.section(axis='X', mode='LAST')
    check(T, "X from off starts a section on X", s.mode == 'SECTION' and s.orientation == 'X', f"{s.mode} {s.orientation}")
    check(T, "plane in the middle", abs(s.offset) < 1e-3, str(s.offset))
    s.offset = 7.0
    with view.override():
        bpy.ops.crosscut.set_mode(mode='SECTION')
    check(T, "turned off", s.mode == 'OFF')
    with view.override():
        bpy.ops.crosscut.section(axis='X', mode='LAST')
    check(T, "same axis again keeps the position", s.mode == 'SECTION' and abs(s.offset - 7.0) < 1e-3, str(s.offset))
    with view.override():
        bpy.ops.crosscut.set_mode(mode='SECTION')
    s.last_mode = 'SLICE'
    with view.override():
        bpy.ops.crosscut.section(axis='Y', mode='LAST')
    check(T, "uses the last mode", s.mode == 'SLICE' and s.orientation == 'Y', f"{s.mode} {s.orientation}")
    # a lit button turns it off, another one re-aims
    with view.override():
        bpy.ops.crosscut.section(axis='X', mode='LAST')
    check(T, "another axis re-aims", s.mode == 'SLICE' and s.orientation == 'X', f"{s.mode} {s.orientation}")
    with view.override():
        bpy.ops.crosscut.section(axis='X', mode='LAST')
    check(T, "the lit axis turns it off", s.mode == 'OFF', s.mode)
    with view.override():
        bpy.ops.crosscut.section(axis='X', mode='LAST')
    check(T, "and back on", s.mode == 'SLICE')
    with view.override():
        bpy.ops.crosscut.from_view(toggle=True)
    check(T, "View turns on the view plane", s.mode == 'SLICE' and s.orientation == 'VIEW')
    with view.override():
        bpy.ops.crosscut.from_view(toggle=True)
    check(T, "the lit View turns it off", s.mode == 'OFF', s.mode)
    with view.override():
        bpy.ops.crosscut.section(axis='Y', mode='LAST')
    with view.override():
        bpy.ops.crosscut.set_mode(mode='SLICE')
    for o in scene.objects:
        o.select_set(False)
    box("part-002", (5, 5, 5), (40, 0, 0))
    s.plane_object = None
    s.last_mode = 'SECTION'
    with view.override():
        bpy.ops.crosscut.section(axis='OBJECT', mode='LAST')
    check(T, "Object with nothing to pick stays on Object, no cut",
          s.orientation == 'OBJECT' and s.mode == 'SECTION' and cc("engine").compute_planes(s) is None,
          f"{s.orientation} {s.mode}")
    check(T, "no draw errors", not errors(), str(errors()))


@test
def clip_scrub(view):
    T = "clip_scrub"
    if not bpy.app.use_event_simulate:
        print("    skipped: run Blender with --enable-event-simulate")
        return
    scene = new_scene("cc-clip-scrub")
    box("part-001", (60, 60, 60))
    s = scene.crosscut
    view.look((0, 0, 0), 300, (0, 0, 0), ortho=True)  # top view
    settings(s, cap_style='SOLID', step=2.0)
    yield 0.1
    yield from settle()
    win = bpy.context.window
    r = view.region
    with view.override():
        bpy.ops.crosscut.clip('INVOKE_DEFAULT')
    yield 0.1
    a, b = view.px((-20, -10, 0)), view.px((20, 10, 0))
    win.event_simulate('MOUSEMOVE', 'NOTHING', x=r.x + a[0], y=r.y + a[1])
    yield 0.05
    win.event_simulate('LEFTMOUSE', 'PRESS', x=r.x + a[0], y=r.y + a[1])
    yield 0.05
    win.event_simulate('MOUSEMOVE', 'NOTHING', x=r.x + b[0], y=r.y + b[1])
    yield 0.05
    win.event_simulate('LEFTMOUSE', 'RELEASE', x=r.x + b[0], y=r.y + b[1])
    yield 0.2
    check(T, "box drawn", view.rv3d.use_clip_planes)
    eng = cc("engine")
    axes = eng.clip_axes(view.rv3d)
    check(T, "two sliders' worth of walls", len(axes) == 2, str(len(axes)))
    labels = [eng.clip_axis_label(x[0]) for x in axes]
    check(T, "labelled by nearest world axis", sorted(labels) == ['X', 'Y'], str(labels))
    check(T, "axes point the positive way", all(float(x[0].max()) > 0.9 for x in axes), str([x[0] for x in axes]))
    ix, iy = labels.index('X'), labels.index('Y')
    check(T, "half widths are the box's", abs(axes[ix][2] - 20.0) < 0.6 and abs(axes[iy][2] - 10.0) < 0.6,
          f"{axes[ix][2]} {axes[iy][2]}")
    view.look((0, 0, 0), 300, (70, 0, 0), ortho=True)
    yield from settle()
    Shot(view, "clip_scrub_start")
    with view.override():
        setattr(s, f"clip_position_{iy + 1}", axes[iy][1] + 8.0)
    moved = eng.clip_axes(view.rv3d)
    check(T, "Y slider moves along Y only", abs(moved[iy][1] - axes[iy][1] - 8.0) < 1e-3
          and abs(moved[ix][1] - axes[ix][1]) < 1e-3, f"{moved[iy][1]} {moved[ix][1]}")
    check(T, "size unchanged", abs(moved[iy][2] - axes[iy][2]) < 1e-3)
    yield from settle()
    Shot(view, "clip_scrub_moved")
    check(T, "caps follow", cc("draw").last_info(r).get("count", 0) >= 1, str(cc("draw").last_info(r)))
    with view.override():
        setattr(s, f"clip_scrub_{ix + 1}", 0.0)
        low = eng.clip_axes(view.rv3d)[ix][1]
        check(T, "slider 0: just clear of the part", abs(low + 30.0 + axes[ix][2]) < 0.6, str(low))
        check(T, "slider reads back", getattr(s, f"clip_scrub_{ix + 1}") < 1e-3)
        setattr(s, f"clip_scrub_{ix + 1}", 1.0)
        high = eng.clip_axes(view.rv3d)[ix][1]
        check(T, "slider 1: just clear on the other side", abs(high - 30.0 - axes[ix][2]) < 0.6, str(high))
        setattr(s, f"clip_scrub_{ix + 1}", 0.5)
        before = eng.clip_axes(view.rv3d)
        bpy.ops.crosscut.step(direction=1, clip_axis=iy)
        after = eng.clip_axes(view.rv3d)
        check(T, "an axis's arrows move along it", abs(after[iy][1] - before[iy][1] - 2.0) < 1e-3
              and abs(after[ix][1] - before[ix][1]) < 1e-3)
        toward = np.array(view.rv3d.view_matrix.inverted())[:3, 2]
        f = eng.clip_facing_axis(view.rv3d)
        check(T, "the wheel uses the walls facing you, toward you", abs(abs(float(f[1])) - 1.0) < 1e-3
              and float(f @ toward) > 0, str(f))
    planes_before = [tuple(p) for p in view.rv3d.clip_planes]
    labels_before = [eng.clip_axis_label(x[0]) for x in eng.clip_axes(view.rv3d)]
    signs_before = [x[0].tolist() for x in eng.clip_axes(view.rv3d)]
    view.look((0, 0, 0), 300, (0, 70, 200), ortho=True)
    yield from settle()
    check(T, "orbiting doesn't move the box", [tuple(p) for p in view.rv3d.clip_planes] == planes_before)
    check(T, "orbiting doesn't relabel or flip the sliders", [eng.clip_axis_label(x[0]) for x in eng.clip_axes(view.rv3d)]
          == labels_before and [x[0].tolist() for x in eng.clip_axes(view.rv3d)] == signs_before)
    Shot(view, "clip_scrub_other_axis")
    view.rv3d.use_clip_planes = False
    check(T, "no draw errors", not errors(), str(errors()))


@test
def clip_memory(view):
    # Clip brings back the box Section or Slice replaced
    T = "clip_memory"
    if not bpy.app.use_event_simulate:
        print("    skipped: run Blender with --enable-event-simulate")
        return
    scene = new_scene("cc-clip-memory")
    box("part-001", (60, 60, 60))
    s = scene.crosscut
    view.look((0, 0, 0), 300, (0, 0, 0), ortho=True)
    settings(s, cap_style='SOLID')
    yield 0.1
    win = bpy.context.window
    r = view.region
    with view.override():
        bpy.ops.crosscut.clip('INVOKE_DEFAULT')
    yield 0.1
    a, b = view.px((-20, -10, 0)), view.px((20, 10, 0))
    win.event_simulate('MOUSEMOVE', 'NOTHING', x=r.x + a[0], y=r.y + a[1])
    yield 0.05
    win.event_simulate('LEFTMOUSE', 'PRESS', x=r.x + a[0], y=r.y + a[1])
    yield 0.05
    win.event_simulate('MOUSEMOVE', 'NOTHING', x=r.x + b[0], y=r.y + b[1])
    yield 0.05
    win.event_simulate('LEFTMOUSE', 'RELEASE', x=r.x + b[0], y=r.y + b[1])
    yield 0.3
    planes = [tuple(round(v, 4) for v in p) for p in view.rv3d.clip_planes]
    check(T, "box drawn", view.rv3d.use_clip_planes)
    with view.override():
        bpy.ops.crosscut.set_mode(mode='SLICE')
    yield 0.2
    yield from settle()
    check(T, "Slice took over", s.mode == 'SLICE' and cc("draw").has_saved_clip(view.rv3d))
    with view.override():
        bpy.ops.crosscut.clip('INVOKE_DEFAULT')
    yield 0.2
    yield from settle()
    now = [tuple(round(v, 4) for v in p) for p in view.rv3d.clip_planes]
    check(T, "Clip brings the same box back", s.mode == 'OFF' and view.rv3d.use_clip_planes and now == planes, str(now[:2]))
    Shot(view, "clip_memory_back")
    info = cc("draw").last_info(r)
    check(T, "it's the region again, with caps", info.get("native") and not info.get("ours"), str(info))
    # Off and on: remembered through turning Section off, too
    with view.override():
        bpy.ops.crosscut.set_mode(mode='SECTION')
    yield 0.2
    with view.override():
        bpy.ops.crosscut.set_mode(mode='SECTION')
    yield 0.2
    yield from settle()
    check(T, "Section off leaves no clipping", not view.rv3d.use_clip_planes)
    with view.override():
        bpy.ops.crosscut.clip('INVOKE_DEFAULT')
    yield 0.2
    now = [tuple(round(v, 4) for v in p) for p in view.rv3d.clip_planes]
    check(T, "still remembered", view.rv3d.use_clip_planes and now == planes)
    # clicking the lit button removes it for good: next time asks for a new one
    with view.override():
        bpy.ops.crosscut.clip('INVOKE_DEFAULT')
    yield 0.2
    check(T, "click when lit removes it", not view.rv3d.use_clip_planes)
    check(T, "and forgets it", not cc("draw").has_saved_clip(view.rv3d))
    check(T, "no draw errors", not errors(), str(errors()))


@test
def tools_through_clipping(view):
    # painting and Edit Mode box select work through Section, Slice and a clipping region
    T = "tools_through_clipping"
    scene = new_scene("cc-paint")
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=40, y_segments=40, size=20.0)
    me = bpy.data.meshes.new("part-001")
    bm.to_mesh(me)
    bm.free()
    ob = _link("part-001", me)
    vg = ob.vertex_groups.new(name="g")
    bpy.context.view_layer.objects.active = ob
    ob.select_set(True)
    s = scene.crosscut
    view.look((0, 0, 0), 80, (0, 0, 0), ortho=True)
    settings(s)
    yield 0.1
    rv = view.rv3d
    area, r, sp = view.area, view.region, view.space

    def over():
        return bpy.context.temp_override(window=view.window, area=area, region=r, space_data=sp, region_data=rv,
                                         active_object=ob, object=ob)

    def paint(co):
        for v in ob.data.vertices:
            vg.remove([v.index])
        x, y = view.px(co)
        valid = bpy.types.OperatorStrokeElement.bl_rna.properties.keys()
        pts = []
        for i in range(6):
            d = {"name": "", "mouse": (x + i * 4, y), "mouse_event": (x + i * 4, y), "pen_flip": False,
                 "is_start": i == 0, "location": tuple(co), "pressure": 1.0, "size": 60.0, "time": float(i),
                 "x_tilt": 0.0, "y_tilt": 0.0}
            pts.append({k: v for k, v in d.items() if k in valid})
        with over():
            bpy.ops.paint.weight_paint(stroke=pts, mode='NORMAL')
        return sum(1 for v in ob.data.vertices for g in v.groups if g.weight > 1e-3)

    with over():
        bpy.ops.object.mode_set(mode='WEIGHT_PAINT')
    yield 0.2
    yield from settle()
    plain = paint((6, 0, 0))
    check(T, "painting works with no clipping (test sees it)", plain > 0, str(plain))
    settings(s, mode='SECTION', orientation='X', offset=0.0, flip=True)  # keeps x >= 0
    yield 0.3
    yield from settle()
    yield 0.2
    yield from settle()
    n = paint((6, 0, 0))
    check(T, "Section: paints on the kept side", n == plain, f"{n} vs {plain}")
    check(T, "Section: not on the side cut away", paint((-6, 0, 0)) == 0)
    x = view.rv3d.view_perspective
    check(T, "the view is left as it was", x == 'ORTHO' and abs(view.rv3d.view_distance - 80) < 1e-3
          and abs(sp.clip_end - 100000.0) < 1e-3, f"{x} {view.rv3d.view_distance} {sp.clip_end}")
    # right up to the cut, on both sides of it
    near_cut = (paint((0.8, 0, 0)), paint((-0.8, 0, 0)))
    check(T, "Section: the box's edge is on the cut", near_cut[0] > near_cut[1], str(near_cut))
    settings(s, mode='SLICE', orientation='X', offset=6.0, thickness=8.0)
    yield 0.3
    yield from settle()
    yield 0.2
    yield from settle()
    check(T, "Slice slab: paints inside it", paint((6, 0, 0)) == plain)
    check(T, "Slice slab: not outside it", paint((-6, 0, 0)) == 0)
    settings(s)
    yield 0.2
    yield from settle()
    with over():
        bpy.ops.view3d.clip_border(xmin=r.width // 2 - 60, xmax=r.width // 2 + 200, ymin=r.height // 2 - 150,
                                   ymax=r.height // 2 + 150, wait_for_input=False)
    yield 0.3
    yield from settle()
    yield 0.2
    yield from settle()
    n = paint((2, 0, 0))
    check(T, "clipping region: paints inside it", n > 0, str(n))
    axes = cc("engine").clip_axes(rv)
    i = [cc("engine").clip_axis_label(a[0]) for a in axes].index('X')
    with over():
        setattr(s, f"clip_position_{i + 1}", axes[i][1] + 300.0)
    yield 0.3
    yield from settle()
    yield 0.2
    yield from settle()
    check(T, "clipping region, scrubbed away: paints nothing there", paint((2, 0, 0)) == 0)
    rv.use_clip_planes = False
    with over():
        bpy.ops.object.mode_set(mode='OBJECT')
    yield 0.2
    # Edit Mode box select
    def box_select():
        with over():
            bpy.ops.object.mode_set(mode='EDIT')
            bpy.ops.mesh.select_all(action='DESELECT')
            ax, ay = view.px((3, -3, 0))
            bx, by = view.px((9, 3, 0))
            bpy.ops.view3d.select_box(xmin=ax, xmax=bx, ymin=ay, ymax=by, mode='SET', wait_for_input=False)
            bpy.ops.object.mode_set(mode='OBJECT')
        return sum(v.select for v in ob.data.vertices)

    plain = box_select()
    check(T, "box select works with no clipping (test sees it)", plain > 0, str(plain))
    settings(s, mode='SECTION', orientation='X', offset=0.0, flip=True)
    yield 0.2
    with over():
        bpy.ops.object.mode_set(mode='EDIT')
    yield 0.2
    yield from settle()
    yield 0.2
    yield from settle()
    with over():
        bpy.ops.object.mode_set(mode='OBJECT')
    n = box_select()
    check(T, "Edit Mode: box select works on the kept side", n == plain, f"{n} vs {plain}")
    settings(s)
    yield 0.1
    # Object Mode: no box or tint left behind
    yield from settle()
    check(T, "no draw errors", not errors(), str(errors()))


@test
def clip_tint(view):
    # Blender's faint box goes by default, and as soon as you scrub with the setting on
    T = "clip_tint"
    if not bpy.app.use_event_simulate:
        print("    skipped: run Blender with --enable-event-simulate")
        return
    scene = new_scene("cc-tint")
    box("part-001", (20, 20, 20), (200, 0, 0))   # clear of the box, which then shows the bare background
    s = scene.crosscut
    view.look((0, 0, 0), 300, (0, 0, 0), ortho=True)
    win = bpy.context.window
    r = view.region

    def draw_box():
        a, b = view.px((-10, -10, 0)), view.px((10, 10, 0))
        with view.override():
            bpy.ops.crosscut.clip('INVOKE_DEFAULT')
        yield 0.1
        win.event_simulate('MOUSEMOVE', 'NOTHING', x=r.x + a[0], y=r.y + a[1])
        yield 0.05
        win.event_simulate('LEFTMOUSE', 'PRESS', x=r.x + a[0], y=r.y + a[1])
        yield 0.05
        win.event_simulate('MOUSEMOVE', 'NOTHING', x=r.x + b[0], y=r.y + b[1])
        yield 0.05
        win.event_simulate('LEFTMOUSE', 'RELEASE', x=r.x + b[0], y=r.y + b[1])
        yield 0.2
        view.look((0, 0, 0), 300, (0, 0, 0), ortho=True)
        yield from settle()

    def draw_box_here():
        a, b = view.px((-10, -10, 0)), view.px((10, 10, 0))
        with view.override():
            bpy.ops.crosscut.clip('INVOKE_DEFAULT')
        yield 0.1
        win.event_simulate('MOUSEMOVE', 'NOTHING', x=r.x + a[0], y=r.y + a[1])
        yield 0.05
        win.event_simulate('LEFTMOUSE', 'PRESS', x=r.x + a[0], y=r.y + a[1])
        yield 0.05
        win.event_simulate('MOUSEMOVE', 'NOTHING', x=r.x + b[0], y=r.y + b[1])
        yield 0.05
        win.event_simulate('LEFTMOUSE', 'RELEASE', x=r.x + b[0], y=r.y + b[1])
        yield 0.2
        yield from settle()

    far = (view.region.width // 8, view.region.height // 2)  # plain background

    def tinted(name):
        shot = Shot(view, name)
        inside, bg = shot.at(view.px((0, 0, 0)), r=2), shot.at(far, r=2)
        return not near(inside, bg, 0), f"{inside} {bg}"

    settings(s, clip_tint=False)
    yield from draw_box()
    on, d = tinted("tint_off")
    check(T, "by default there's no tint", not on and view.rv3d.use_clip_planes, d)
    n = len(cc("engine").clip_axes(view.rv3d))
    check(T, "the region's planes survive", n == 2, str(n))
    s.clip_tint = True
    yield 0.1
    yield from settle()
    on, d = tinted("tint_on")
    check(T, "turning it on shows it, without a new box", on, d)
    s.clip_tint = False
    yield from settle()
    on, d = tinted("tint_off_again")
    check(T, "off again hides it", not on, d)
    s.clip_tint = True
    yield from settle()
    on, d = tinted("tint_on_again")
    check(T, "and back on shows it", on, d)
    with view.override():
        bpy.ops.crosscut.set_mode(mode='SLICE')
    yield 0.2
    yield from settle()
    on, d = tinted("tint_during_slice")
    with view.override():
        bpy.ops.crosscut.clip('INVOKE_DEFAULT')
    yield 0.2
    yield from settle()
    on, d = tinted("tint_after_slice")
    check(T, "Slice and back keeps it", on and view.rv3d.use_clip_planes, d)
    # it follows a scrub
    axes = cc("engine").clip_axes(view.rv3d)
    with view.override():
        s.clip_position_1 = axes[0][1] + 40.0
        s.clip_position_2 = axes[1][1] + 40.0
    yield 0.1
    yield from settle()
    on, d = tinted("tint_scrubbed")
    check(T, "it moves with the box: the old place is clear", not on, d)
    # in perspective, where a box's walls meet at the eye, and after orbiting
    with view.override():
        bpy.ops.crosscut.clip('INVOKE_DEFAULT')  # removes it
    yield 0.1
    view.look((0, 0, 0), 300, (0, 0, 0))
    yield from settle()
    yield from draw_box_here()
    shot = Shot(view, "tint_perspective")
    inside, bg = shot.at(view.px((0, 0, 0)), r=2), shot.at(far, r=2)
    check(T, "perspective: shows", not near(inside, bg, 2), f"{inside} {bg}")
    view.look((0, 0, 0), 300, (50, 0, 40))
    yield from settle()
    Shot(view, "tint_perspective_orbit")
    view.rv3d.use_clip_planes = False
    check(T, "no draw errors", not errors(), str(errors()))


@test
def random_colors(view):
    # in Random shading the caps match what Blender draws on the parts
    T = "random_colors"
    scene = new_scene("cc-random")
    a = box("part-001", (30, 30, 30), (-30, 0, 0))
    b = box("Some Part.002", (30, 30, 30), (30, 0, 0))
    s = scene.crosscut
    view.space.shading.color_type = 'RANDOM'
    view.space.shading.light = 'FLAT'
    view.look((0, 0, 0), 300, (60, 0, 0), ortho=True)
    settings(s, mode='SECTION', orientation='Z', color_source='AUTO', cap_style='SOLID', outline=False)
    yield 0.05
    yield from settle()
    shot = Shot(view, "random_colors")
    for ob, x in ((a, -30), (b, 30)):
        top, side = shot.at(view.px((x, 0, 0))), shot.at(view.px((x, -15, -8)))
        check(T, f"{ob.name}: cap matches the part", near(top, side, 3), f"{top} {side}")
    # the Fill settings take a followed color down
    p = view.px((-30, 0, 0))
    full = shot.at(p)
    s.fill_brightness = 0.5
    yield from settle()
    dark = Shot(view, "random_colors_dark").at(p)
    check(T, "Brightness darkens it", max(dark) < max(full) - 30, f"{dark} {full}")
    s.fill_brightness, s.fill_saturation = 1.0, 0.0
    yield from settle()
    gray = Shot(view, "random_colors_gray").at(p)
    check(T, "Saturation grays it", max(gray) - min(gray) < 4 < max(full) - min(full), f"{gray} {full}")
    s.fill_saturation, s.fill_tint_amount, s.fill_tint = 1.0, 1.0, (1.0, 0.0, 0.0)
    yield from settle()
    tinted = Shot(view, "random_colors_tint").at(p)
    check(T, "Tint mixes in", tinted[0] > 200 and tinted[1] < 30, f"{tinted}")
    # over the part's own inside, which Flat light shows in its full colour
    s.fill_tint_amount, s.fill_brightness = 0.0, 0.3
    yield from settle()
    solid = Shot(view, "random_colors_opaque").at(p)
    s.fill_opacity = 0.5
    yield from settle()
    half = Shot(view, "random_colors_opacity").at(p)
    check(T, "Fill Opacity lets things through", max(half) > max(solid) + 15, f"{half} {solid}")
    view.space.shading.color_type = 'OBJECT'
    view.space.shading.light = 'STUDIO'
    check(T, "no draw errors", not errors(), str(errors()))


@test
def overlays_off(view):
    T = "overlays_off"
    scene = new_scene("cc-overlays")
    box("part-001", (30, 30, 30), open_top=True)
    s = scene.crosscut
    view.look((0, 0, 0), 200, (60, 0, 30))
    settings(s, mode='SECTION', orientation='X', flip=True, plane_display='TINT', plane_opacity=0.3)
    yield 0.05
    yield from settle()
    corner = view.px((0, 16.4, 16.4))
    on = Shot(view, "overlays_on")
    view.space.overlay.show_overlays = False
    yield from settle()
    off = Shot(view, "overlays_off")
    bg = bg_of(off, view)
    check(T, "plane hides with overlays", not near(on.at(corner), bg, 4) and near(off.at(corner), bg, 4),
          f"{on.at(corner)} {off.at(corner)} {bg}")
    readout_area = off.px[off.oy + 8:off.oy + 30, off.ox + view.region.width // 3:off.ox + 2 * view.region.width // 3]
    check(T, "readout hides with overlays", int(np.ptp(readout_area, axis=(0, 1)).max()) <= 3)
    # measuring lines go with their lengths
    dr = cc("draw")
    dr._measure["dims"].append((np.array((-60.0, 40.0, 0.0)), np.array((60.0, 40.0, 0.0)), "1"))
    yield from settle()
    spot = view.px((50, 40, 0))
    gone = Shot(view, "overlays_off_line").at(spot, r=0)
    view.space.overlay.show_overlays = True
    yield from settle()
    shown = Shot(view, "overlays_on_line").at(spot, r=0)
    dr.measure_clear()
    check(T, "a pinned line hides with overlays", near(gone, bg, 4) and not near(shown, bg, 4), f"{gone} {shown}")
    check(T, "no draw errors", not errors(), str(errors()))


@test
def face_orientation(view):
    T = "face_orientation"
    scene = new_scene("cc-face")
    ob = box("part-001", (30, 30, 30))
    s = scene.crosscut
    view.look((0, 0, 0), 200, (60, 0, 30))
    settings(s, mode='SECTION', orientation='Z')
    yield 0.05
    yield from settle()
    info = cc("draw").last_info(view.region)
    check(T, "a healthy part isn't flagged", not info.get("inside_out") and not info.get("mixed_normals"), str(info))
    for p in ob.data.polygons:
        p.flip()
    ob.data.update()
    yield 0.1
    yield from settle()
    info = cc("draw").last_info(view.region)
    severe = cc("draw").readout_lines(scene, s, info)[2]
    check(T, "inside out: named in red", info.get("inside_out") == ["part-001"] and any("Inside out" in w for w in severe),
          f"{info} {severe}")
    shot = Shot(view, "inside_out")
    check(T, "inside out: still capped", is_green(shot.at(view.px((0, 0, 0)))))
    ob.data.polygons[0].flip()
    ob.data.update()
    yield 0.1
    yield from settle()
    info = cc("draw").last_info(view.region)
    check(T, "one face flipped the other way: mixed normals", info.get("mixed_normals") == ["part-001"]
          or info.get("inside_out") == ["part-001"], str(info))
    # a cap seen from inside the part, with Face Orientation on, is the backface colour
    bpy.data.objects.remove(ob)
    box("part-002", (30, 30, 30), open_top=True)
    settings(s, mode='SECTION', orientation='Y', offset=0.0, flip=False)  # keeps y < 0
    view.space.overlay.show_face_orientation = True
    view.look((0, 0, 0), 200, (20, 0, 0))     # from -y, through the open top: the viewer is on the kept side
    yield 0.1
    yield from settle()
    back = Shot(view, "cap_from_behind").at(view.px((0, 0, 10)))
    view.look((0, 0, 0), 200, (20, 0, 180))   # from +y: the cut side
    yield from settle()
    front = Shot(view, "cap_from_front").at(view.px((0, 0, 10)))
    view.space.overlay.show_face_orientation = False
    check(T, "from inside with Face Orientation: reads red", is_red(back), f"{back}")
    check(T, "from the cut side: its own colour", is_green(front), f"{front}")
    # a zero-thickness slice has no inside: both sides keep the cap's colour
    settings(s, mode='SLICE', orientation='Y', offset=0.0)
    view.space.overlay.show_face_orientation = True
    for name, rot in (("a", (20, 0, 0)), ("b", (20, 0, 180))):
        view.look((0, 0, 0), 200, rot)
        yield 0.1
        yield from settle()
        c = Shot(view, f"slice_side_{name}").at(view.px((0, 0, 10)))
        check(T, f"zero-thickness slice, side {name}: not red", is_green(c), f"{c}")
    view.space.overlay.show_face_orientation = False
    check(T, "no draw errors", not errors(), str(errors()))


@test
def annotations_over_caps(view):
    T = "annotations_over_caps"
    scene = new_scene("cc-annot")
    box("part-001", (60, 60, 30))
    s = scene.crosscut
    view.look((0, 0, 0), 200, (0, 0, 0), ortho=True)
    settings(s, mode='OFF', orientation='Z')
    with view.override():
        bpy.ops.gpencil.annotation_add()
        data = bpy.context.annotation_data
    layer = data.layers.new("note")
    layer.color = (1.0, 0.2, 0.9)
    layer.thickness = 8
    frame = layer.frames.new(scene.frame_current)
    st = frame.strokes.new()
    st.display_mode = '3DSPACE'
    st.points.add(2)
    st.points[0].co = (-20, 10, 20)
    st.points[1].co = (20, 10, 20)
    yield 0.1
    yield from settle()
    vanilla = Shot(view, "annotation_vanilla").at(view.px((0, 10, 20)), r=0)
    # section: the stroke sits above the plane, in clipped space, over the cap
    settings(s, mode='SECTION', orientation='Z')
    yield 0.1
    yield from settle()
    shot = Shot(view, "annotation_over_cap")
    c = shot.at(view.px((0, 10, 20)), r=0)
    check(T, "annotation shows over the cap, in its own colour", near(c, vanilla, 12), f"{c} vanilla {vanilla}")
    c = shot.at(view.px((0, -15, 0)), r=1)
    check(T, "the cap is there", is_green(c), f"{c}")
    view.space.overlay.show_annotation = False
    yield from settle()
    c = Shot(view, "annotation_hidden").at(view.px((0, 10, 20)), r=0)
    check(T, "hides with its overlay toggle", is_green(c), f"{c}")
    view.space.overlay.show_annotation = True
    check(T, "no draw errors", not errors(), str(errors()))


@test
def hatch_scale(view):
    T = "hatch_scale"
    scene = new_scene("cc-hatchscale")
    box("part-001", (100, 100, 50), (0, 0, 0))
    s = scene.crosscut
    yield 0.01
    settings(s, hatch_space='MODEL')
    s.hatch_pitch = 2.0
    s.hatch_scale = 0.5
    size = float(np.linalg.norm((100, 100, 50)))
    v = cc("draw")._hatch_vec(s, 0, 'HATCH', size=size)
    check(T, "half way: spacing follows the square root of size", abs(abs(v[0]) - 2.0 * (size / 50.0) ** 0.5) < 1e-4, str(v))
    s.hatch_vary = False
    v0 = cc("draw")._hatch_vec(s, 0, 'HATCH', size=50.0)
    v1 = cc("draw")._hatch_vec(s, 0, 'HATCH', size=200.0)
    check(T, "a 50 unit part gets the setting", abs(v0[0] - 2.0) < 1e-5, str(v0))
    check(T, "four times the size, twice the spacing", abs(v1[0] - 4.0) < 1e-5, str(v1))
    s.hatch_scale = 0.0
    v2 = cc("draw")._hatch_vec(s, 0, 'HATCH', size=200.0)
    check(T, "at 0 size doesn't matter", abs(v2[0] - 2.0) < 1e-5, str(v2))
    s.hatch_space = 'SCREEN'
    v3 = cc("draw")._hatch_vec(s, 0, 'HATCH', size=200.0)
    check(T, "screen space ignores size", v3[0] < 0, str(v3))
    s.hatch_scale = 0.5
    s.hatch_vary = True


@test
def measure_overlap(view):
    T = "measure_overlap"
    scene = new_scene("cc-measure")
    box("part-001", (40, 30, 30), (-15, 0, 0))    # spans x -35..5
    box("part-002", (40, 30, 30), (20, 0, 0))     # spans x 0..40: overlap x 0..5
    s = scene.crosscut
    view.look((0, 0, 0), 200, (0, 0, 0), ortho=True)
    settings(s, mode='SECTION', orientation='Z', cap_style='HATCH', color_source='OBJECT')
    yield 0.05
    yield from settle()
    dr = cc("draw")
    r = view.region
    with view.override():
        res = dr._measure_at(bpy.context, r, r.x + view.px((2.5, 0, 0))[0], r.y + view.px((2.5, 0, 0))[1])
        check(T, "the overlap's depth", res is not None and abs(res["max"][2] - 5.0) < 0.1, str(res))
        s.measure_local = False
        res2 = dr._measure_at(bpy.context, r, r.x + view.px((2.5, 0, 0))[0], r.y + view.px((2.5, 0, 0))[1])
        check(T, "Local Width off: one measure", res2 is not None and res2["local"] is None)
        s.measure_local = True
        px = view.px((-20, 0, 0))
        res3 = dr._measure_at(bpy.context, r, r.x + px[0], r.y + px[1])
        check(T, "over one part: its thickness at the mouse, no max", res3 is not None and res3["max"] is None
              and abs(res3["local"][2] - 30.0) < 0.5, str(res3))
        s.measure_section_max = True
        res3 = dr._measure_at(bpy.context, r, r.x + px[0], r.y + px[1])
        check(T, "Section Max on: the greatest too", res3["max"] is not None and res3["max"][2] > 29.0, str(res3))
        s.measure_section_max = False
        s.measure_ignore_overlaps = True
        res3 = dr._measure_at(bpy.context, r, r.x + view.px((2.5, 0, 0))[0], r.y + view.px((2.5, 0, 0))[1])
        check(T, "Ignore Overlaps: thickness even over an overlap", res3["max"] is None and abs(res3["local"][2] - 40.0) < 1.5,
              str(res3))
        s.measure_ignore_overlaps = False
    if bpy.app.use_event_simulate:
        win = bpy.context.window
        with view.override():
            bpy.ops.crosscut.measure('INVOKE_DEFAULT')
        check(T, "on", dr.measure_running())
        yield 0.1
        x, y = view.px((2.5, 3, 0))
        win.event_simulate('MOUSEMOVE', 'NOTHING', x=r.x + x, y=r.y + y)
        yield 0.3
        yield from settle()
        Shot(view, "measure_overlap")
        check(T, "hover shows it", "5.0" in dr._measure["text"] or "4.9" in dr._measure["text"], dr._measure["text"])
        s.measure_max = False
        win.event_simulate('MOUSEMOVE', 'NOTHING', x=r.x + x + 1, y=r.y + y)
        yield 0.3
        check(T, "Max Width off: no max line", dr._measure["a"] is None, str(dr._measure["text"]))
        s.measure_max = True
        x, y = view.px((-200, 0, 0))
        win.event_simulate('MOUSEMOVE', 'NOTHING', x=r.x + x, y=r.y + y)
        yield 0.3
        check(T, "leaving clears it", dr._measure["a"] is None)
        # two round parts: away from the deepest place, the local width is less than the greatest depth
        for ob in list(scene.objects):
            bpy.data.objects.remove(ob)
        cylinder("part-001", 30, 30, (-26, 0, 0), (0.3, 0.55, 0.85))
        cylinder("part-002", 30, 30, (26, 0, 0), (0.9, 0.6, 0.2))
        view.look((0, 0, 0), 120, (0, 0, 0), ortho=True)
        s.overlap_style = 'BLEND'
        yield 0.1
        yield from settle()
        x, y = view.px((0, 11, 0))
        win.event_simulate('MOUSEMOVE', 'NOTHING', x=r.x + x, y=r.y + y)
        yield 0.3
        yield from settle()
        Shot(view, "measure_two_lines")
        m = dr._measure
        check(T, "two measures, labelled", m["la"] is not None and m["text"].startswith("max ") and bool(m["ltext"]),
              f"{m['text']} / {m['ltext']}")
        max_d = float(np.linalg.norm(np.asarray(m["a"]) - m["b"]))
        loc_d = float(np.linalg.norm(np.asarray(m["la"]) - m["lb"])) if m["la"] is not None else 0.0
        check(T, "the local width is narrower here", 0.0 < loc_d < max_d - 0.2, f"{loc_d} {max_d}")
        # click a line: its nearer end stays, the other follows the mouse along its contour
        before_sel = [o.name for o in bpy.context.selected_objects]
        la_hover = np.asarray(m["la"]).copy()
        end = view.px(tuple(la_hover))
        win.event_simulate('MOUSEMOVE', 'NOTHING', x=r.x + end[0], y=r.y + end[1])
        yield 0.2
        local_now = dr._measure["la"]
        check(T, "still a line to click", local_now is not None)
        fixed_expect = None
        if local_now is not None:
            near_end = min((dr._measure["la"], dr._measure["lb"]), key=lambda q: np.linalg.norm(np.asarray(q) - la_hover))
            fixed_expect = np.asarray(near_end).copy()
        win.event_simulate('LEFTMOUSE', 'PRESS', x=r.x + end[0], y=r.y + end[1])
        win.event_simulate('LEFTMOUSE', 'RELEASE', x=r.x + end[0], y=r.y + end[1])
        yield 0.2
        pin = dr._measure["anchor"]
        check(T, "click anchors the nearer end", pin is not None and np.allclose(pin["a"], fixed_expect, atol=1e-3)
              if fixed_expect is not None else False, str(pin and pin["a"]))
        check(T, "the click doesn't select anything", [o.name for o in bpy.context.selected_objects] == before_sel)
        length0 = float(np.linalg.norm(pin["a"] - pin["b"])) if pin else 0.0
        if pin:
            win.event_simulate('MOUSEMOVE', 'NOTHING', x=r.x + end[0], y=r.y + end[1] + 60)
            yield 0.2
            yield from settle()
            Shot(view, "measure_anchored")
            check(T, "the anchor stays put", np.allclose(pin["a"], fixed_expect, atol=1e-3))
            length1 = float(np.linalg.norm(pin["a"] - pin["b"]))
            check(T, "the other end moves, so the length changes", abs(length1 - length0) > 0.01, f"{length0} {length1}")
            # still on the other part's circle (radius 30)
            b = np.asarray(pin["b"])
            on_circle = min(abs(np.hypot(b[0] + 26, b[1]) - 30), abs(np.hypot(b[0] - 26, b[1]) - 30))
            check(T, "and stays on a contour", on_circle < 0.1, str(on_circle))
            win.event_simulate('LEFTMOUSE', 'PRESS', x=r.x + end[0], y=r.y + end[1] + 60)
            win.event_simulate('LEFTMOUSE', 'RELEASE', x=r.x + end[0], y=r.y + end[1] + 60)
            yield 0.2
            check(T, "a second click pins it", len(dr._measure["dims"]) == 1 and dr._measure["anchor"] is None)
        # and it carries on: another line, and another pin
        x, y = view.px((0, -6, 0))
        win.event_simulate('MOUSEMOVE', 'NOTHING', x=r.x + x, y=r.y + y)
        yield 0.2
        win.event_simulate('LEFTMOUSE', 'PRESS', x=r.x + x, y=r.y + y)
        win.event_simulate('LEFTMOUSE', 'RELEASE', x=r.x + x, y=r.y + y)
        yield 0.2
        check(T, "another line anchors", dr._measure["anchor"] is not None)
        win.event_simulate('ESC', 'PRESS', x=r.x + x, y=r.y + y)
        win.event_simulate('ESC', 'RELEASE', x=r.x + x, y=r.y + y)
        yield 0.2
        check(T, "Esc while placing drops only that line", dr._measure["anchor"] is None and len(dr._measure["dims"]) == 1
              and dr.measure_running())
        win.event_simulate('LEFTMOUSE', 'PRESS', x=r.x + x + 1, y=r.y + y)
        win.event_simulate('LEFTMOUSE', 'RELEASE', x=r.x + x + 1, y=r.y + y)
        yield 0.2
        x, y = view.px((-110, 0, 0))
        win.event_simulate('MOUSEMOVE', 'NOTHING', x=r.x + x, y=r.y + y)
        yield 0.3
        Shot(view, "measure_pinned")
        check(T, "leaving clears both", dr._measure["a"] is None and dr._measure["la"] is None)
        win.event_simulate('ESC', 'PRESS', x=r.x + x, y=r.y + y)
        win.event_simulate('ESC', 'RELEASE', x=r.x + x, y=r.y + y)
        yield 0.2
        check(T, "Esc stops it", not dr.measure_running())
        check(T, "and leaves the pinned lines", len(dr._measure["dims"]) == 1, str(len(dr._measure["dims"])))
        yield from settle()
        Shot(view, "measure_pinned_after_stop")
        # (Esc only reaches the viewport's keymap with the mouse over it)
        x, y = r.width // 3, r.height // 2
        win.event_simulate('MOUSEMOVE', 'NOTHING', x=r.x + x, y=r.y + y)
        yield 0.1
        s.measure_keep = True
        win.event_simulate('ESC', 'PRESS', x=r.x + x, y=r.y + y)
        win.event_simulate('ESC', 'RELEASE', x=r.x + x, y=r.y + y)
        yield 0.2
        check(T, "Keep Pinned Lines: Esc leaves them", len(dr._measure["dims"]) == 1)
        with view.override():
            bpy.ops.crosscut.measure_clear('INVOKE_DEFAULT')
        check(T, "the Clear button clears them anyway", not dr._measure["dims"])
        s.measure_keep = False
        dr._measure["dims"].append((np.zeros(3), np.array((1.0, 0.0, 0.0)), "1"))
        win.event_simulate('ESC', 'PRESS', x=r.x + x, y=r.y + y)
        win.event_simulate('ESC', 'RELEASE', x=r.x + x, y=r.y + y)
        yield 0.2
        check(T, "a second Esc clears them", not dr._measure["dims"])
        # lengths follow the hatch space
        def text_px():
            yield from settle()  # the redraw resets the context, so read it after
            with view.override():
                sizes.append(dr._measure_text_px(bpy.context, s, (0, 0, 0)))

        sizes = []
        s.hatch_space = 'SCREEN'
        yield from text_px()
        view.look((0, 0, 0), 240, (0, 0, 0), ortho=True)
        yield from text_px()
        s.hatch_space = 'MODEL'
        s.measure_text_height = 4.0
        yield from text_px()
        view.look((0, 0, 0), 120, (0, 0, 0), ortho=True)
        yield from text_px()
        screen_a, screen_b, model_b, model_a = sizes
        check(T, "Screen space: text stays the same size", abs(screen_a - screen_b) < 1e-3, f"{screen_a} {screen_b}")
        check(T, "Model space: zooming out shrinks it with the view", abs(model_a / model_b - 2.0) < 0.05,
              f"{model_a} {model_b}")
        s.hatch_space = 'SCREEN'
        # a wall: anchored on its inner edge, the outer end slides around the outer edge
        for ob in list(scene.objects):
            bpy.data.objects.remove(ob)
        hollow_sphere("part-001", 40, 25, segs=128)
        view.look((0, 0, 0), 120, (0, 0, 0), ortho=True)
        settings(s, mode='SECTION', orientation='Z', cap_style='HATCH', color_source='OBJECT')
        yield 0.1
        yield from settle()
        with view.override():
            bpy.ops.crosscut.measure('INVOKE_DEFAULT')
        yield 0.1
        x, y = view.px((26, 0, 0))
        win.event_simulate('MOUSEMOVE', 'NOTHING', x=r.x + x, y=r.y + y)
        yield 0.2
        check(T, "a wall's thickness", dr._measure["la"] is not None and abs(float(np.linalg.norm(
            np.asarray(dr._measure["la"]) - dr._measure["lb"])) - 15.0) < 0.5, dr._measure["ltext"])
        win.event_simulate('LEFTMOUSE', 'PRESS', x=r.x + x, y=r.y + y)
        win.event_simulate('LEFTMOUSE', 'RELEASE', x=r.x + x, y=r.y + y)
        yield 0.2
        pin = dr._measure["anchor"]
        check(T, "anchored on the inner edge", pin is not None and abs(float(np.linalg.norm(pin["a"][:2])) - 25.0) < 0.2)
        before = np.asarray(pin["b"]).copy()
        win.event_simulate('MOUSEMOVE', 'NOTHING', x=r.x + x + 1, y=r.y + y)
        yield 0.1
        check(T, "a nudge doesn't move the line", np.allclose(pin["b"], before), str(pin["b"]))
        x2, y2 = view.px((30, 12, 0))
        win.event_simulate('MOUSEMOVE', 'NOTHING', x=r.x + x2, y=r.y + y2)
        yield 0.2
        yield from settle()
        Shot(view, "measure_wall_anchored")
        # the cursor is on the line, in the wall, with no need to overshoot
        cur = np.array((30.0, 12.0))
        along = pin["b"][:2] - pin["a"][:2]
        off = abs(float(np.cross(along / np.linalg.norm(along), cur - pin["a"][:2])))
        check(T, "the line runs through the cursor", off < 0.2, str(off))
        win.event_simulate('MOUSEMOVE', 'NOTHING', x=r.x + view.px((60, 20, 0))[0], y=r.y + view.px((60, 20, 0))[1])
        yield 0.2
        outside = np.array((60.0, 20.0))
        direct = 40.0 * outside / np.linalg.norm(outside)
        check(T, "outside it, the nearest point on the edge", np.linalg.norm(pin["b"][:2] - direct) < 0.3, str(pin["b"]))
        win.event_simulate('MOUSEMOVE', 'NOTHING', x=r.x + x2, y=r.y + y2)
        yield 0.2
        out = float(np.linalg.norm(pin["b"][:2]))
        check(T, "the free end slides round the outer edge", abs(out - 40.0) < 0.2 and abs(float(pin["b"][1])) > 3.0,
              f"{out} {pin['b']}")
        win.event_simulate('LEFTMOUSE', 'PRESS', x=r.x + x2, y=r.y + y2)
        win.event_simulate('LEFTMOUSE', 'RELEASE', x=r.x + x2, y=r.y + y2)
        yield 0.2
        x3, y3 = view.px((0, 30, 0))
        win.event_simulate('MOUSEMOVE', 'NOTHING', x=r.x + x3, y=r.y + y3)
        yield 0.2
        yield from settle()
        Shot(view, "measure_wall_pinned")
        check(T, "pinned, with a new line hovering", len(dr._measure["dims"]) == 1 and dr._measure["la"] is not None)
        win.event_simulate('ESC', 'PRESS', x=r.x + x3, y=r.y + y3)
        win.event_simulate('ESC', 'RELEASE', x=r.x + x3, y=r.y + y3)
        yield 0.2
        dr.measure_clear()
        check(T, "and clears the pinned lines", not dr._measure["dims"])
    dr.measure_stop()
    check(T, "no draw errors", not errors(), str(errors()))


@test
def alt_b_button(view):
    T = "alt_b_button"
    scene = new_scene("cc-altb-button")
    box("part-001", (30, 30, 30))
    s = scene.crosscut
    view.look((0, 0, 0), 160, (60, 0, 30))
    settings(s, mode='SECTION', orientation='Z')
    yield 0.1
    yield from settle()
    if not bpy.app.use_event_simulate:
        print("  (no --enable-event-simulate: drawing the box is not tested)")
        return
    win = bpy.context.window
    r = view.region
    # as from the sidebar button: Crosscut turns off and Blender waits for a box
    view.space.show_region_ui = True
    ui = next(rg for rg in view.area.regions if rg.type == 'UI')
    with bpy.context.temp_override(window=win, area=view.area, region=ui):
        bpy.ops.crosscut.clip('INVOKE_DEFAULT')
    check(T, "Section turned off", s.mode == 'OFF', s.mode)
    yield 0.1
    a, b = view.px((-12, -12, 15)), view.px((12, 12, 15))
    x0, x1 = sorted((a[0], b[0]))
    y0, y1 = sorted((a[1], b[1]))
    win.event_simulate('MOUSEMOVE', 'NOTHING', x=r.x + x0, y=r.y + y0)
    yield 0.05
    win.event_simulate('LEFTMOUSE', 'PRESS', x=r.x + x0, y=r.y + y0)
    yield 0.05
    win.event_simulate('MOUSEMOVE', 'NOTHING', x=r.x + x1, y=r.y + y1)
    yield 0.05
    win.event_simulate('LEFTMOUSE', 'RELEASE', x=r.x + x1, y=r.y + y1)
    yield 0.1
    yield from settle()
    Shot(view, "alt_b_button_box")
    check(T, "box drawn: native clipping on", view.rv3d.use_clip_planes and s.mode == 'OFF')
    check(T, "box drawn: caps on it", cc("draw").last_info(r).get("native"), str(cc("draw").last_info(r)))
    with bpy.context.temp_override(window=win, area=view.area, region=ui):
        bpy.ops.crosscut.clip('INVOKE_DEFAULT')
    yield from settle()
    check(T, "clicked again: box removed", not view.rv3d.use_clip_planes)
    view.space.show_region_ui = False
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

    # 2) An Alt+B box exists: Crosscut on replaces it, off leaves no clipping. Blender
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
        bpy.ops.crosscut.set_mode(mode='SECTION')
    yield 0.1
    yield from settle()
    off = Shot(view, "handoff_off_after_altb")
    check(T, "off: no clipping left, not the old Alt+B box", not view.rv3d.use_clip_planes)
    check(T, "off: no box shading", shaded(off) < 200, f"{shaded(off)} px")
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
def select_slice(view):
    """Parts stay click-selectable in a zero-thickness slice (needs --enable-event-simulate)."""
    T = "select_slice"
    if not bpy.app.use_event_simulate:
        print("    skipped: run Blender with --enable-event-simulate")
        return
    scene = new_scene("cc-select")
    a = box("part-001", (30, 30, 30), (-25, 0, 0))
    b = box("part-002", (30, 30, 30), (25, 0, 0))
    s = scene.crosscut
    view.look((0, 0, 0), 200, (0, 0, 0), ortho=True)  # top view
    settings(s, mode='SLICE', orientation='Z', offset=0.0, thickness=0.0)
    for o in scene.objects:
        o.select_set(False)
    yield from settle()
    win = view.window

    def click(co, shift=False):
        x, y = view.px(co)
        x += view.region.x
        y += view.region.y
        win.event_simulate(type='MOUSEMOVE', value='NOTHING', x=x, y=y)
        win.event_simulate(type='LEFTMOUSE', value='PRESS', x=x, y=y, shift=shift)
        win.event_simulate(type='LEFTMOUSE', value='RELEASE', x=x, y=y, shift=shift)

    click((-25, 0, 0))
    yield 0.3
    check(T, "click on a section selects that part", a.select_get() and not b.select_get(),
          f"{a.select_get()} {b.select_get()}")
    click((25, 0, 0), shift=True)
    yield 0.3
    check(T, "shift-click adds the other part", a.select_get() and b.select_get()
          and bpy.context.view_layer.objects.active == b)
    # everything is clipped, so the cut contour has to show the selection
    yield from settle()
    shot = Shot(view, "select_slice_outlines")
    th = bpy.context.preferences.themes[0].view_3d
    sel = tuple(int(round(c * 255)) for c in th.object_selected)
    act = tuple(int(round(c * 255)) for c in th.object_active)

    def edge_has(co, ref):
        x, y = view.px(co)
        return any(near(shot.at((x + dx, y), r=0), ref, 40) for dx in range(-3, 4))
    check(T, "selected part's contour in the selection colour", edge_has((-40, 0, 0), sel), str(sel))
    check(T, "active part's contour in the active colour", edge_has((40, 0, 0), act), str(act))
    # empty space: the click goes on to Blender's own select, so it must do
    # whatever Blender does with Crosscut off
    click((0, 60, 0))
    yield 0.3
    ours = (a.select_get(), b.select_get())
    a.select_set(True)
    b.select_set(True)
    s.mode = 'OFF'
    yield from settle()
    click((0, 60, 0))
    yield 0.3
    plain = (a.select_get(), b.select_get())
    check(T, "click on empty space: same as Blender without Crosscut", ours == plain, f"{ours} vs {plain}")
    check(T, "no draw errors", not errors(), str(errors()))


@test
def object_plane_and_plane_tint(view):
    T = "object_plane_and_plane_tint"
    scene = new_scene("cc-objplane")
    part = hollow_sphere("part-001", 40, 25)
    s = scene.crosscut
    view.look((0, 0, 0), 220, (55, 0, 30))
    settings(s, mode='SECTION', orientation='Z', offset=0.0)
    yield from settle()
    # one visible object, no Empty: it becomes its own plane (local Z through its origin), still capped
    s.plane_object = None
    s.orientation = 'OBJECT'
    check(T, "only object visible: picked as the plane", s.plane_object == part, str(s.plane_object))
    yield from settle()
    shot = Shot(view, "object_plane_self")
    check(T, "part used as its own plane is still capped", is_green(shot.at(view.px((0, -32, 0)))),
          f"{shot.at(view.px((0, -32, 0)))}")
    # no object at all: nothing is cut, and the readout says why
    s.plane_object = None
    yield from settle()
    info = cc("draw").last_info(view.region)
    check(T, "no plane object: no clipping", not view.rv3d.use_clip_planes, str(info))
    lines, warn, _severe = cc("draw").readout_lines(scene, s, info)
    check(T, "no plane object: readout asks for one", any("pick an object" in w for w in warn), str(warn))
    # one Empty among parts: the Empty is picked, and the plane goes through it
    e = bpy.data.objects.new("plane-empty", None)
    scene.collection.objects.link(e)
    e.location = (0, 0, 10)
    s.orientation = 'Z'
    s.orientation = 'OBJECT'
    check(T, "one Empty: picked, plane through it", s.plane_object == e and abs(s.offset) < 1e-6,
          f"{s.plane_object} {s.offset}")
    # the chosen object is hidden later: choosing Object again doesn't stay stuck on it
    e.hide_set(True)
    s.orientation = 'Z'
    s.orientation = 'OBJECT'
    check(T, "hidden plane object: replaced by the only visible object", s.plane_object == part,
          str(s.plane_object))
    e.hide_set(False)
    s.orientation = 'Z'
    s.orientation = 'OBJECT'

    # wire-display solids aren't capped: the readout says so
    w = box("bucket-01", (120, 120, 120), color=(0.5, 0.5, 0.5))
    w.display_type = 'WIRE'
    settings(s, mode='SECTION', orientation='Z', offset=0.0)
    yield from settle()
    lines, warn, _severe = cc("draw").readout_lines(scene, s, cc("draw").last_info(view.region))
    check(T, "wire object: readout warns it isn't capped", any("bucket-01" in x for x in warn), str(warn))
    s.plane_object = None
    bpy.data.objects.remove(w)
    bpy.data.objects.remove(e)

    # slab tint: second plane in its own colour, and no double tint where you look through both
    settings(s, mode='SLICE', orientation='Z', offset=0.0, thickness=10.0, plane_display='NONE')
    yield from settle()
    plain = Shot(view, "slab_no_plane")
    settings(s, mode='SLICE', orientation='Z', offset=0.0, thickness=10.0, plane_display='TINT',
             plane_opacity=0.3)
    yield from settle()
    tint = Shot(view, "slab_tint")
    both = view.px((44, 10, 5))       # off the part, on the upper plane with the lower one behind it
    lower = view.px((0, -44, -5))     # in front of the part, only the lower plane
    db = [t - p for t, p in zip(tint.at(both), plain.at(both), strict=True)]
    dl = [t - p for t, p in zip(tint.at(lower), plain.at(lower), strict=True)]
    check(T, "slab: upper plane bluish, lower plane amber", db[2] > db[0] and dl[0] > dl[2], f"both {db} lower {dl}")
    mb, ml = max(map(abs, db)), max(map(abs, dl))
    check(T, "slab: no double tint through both planes", 0.5 < mb / max(ml, 1) < 2.0, f"{mb} vs {ml}")
    op = s.bl_rna.properties["plane_opacity"]
    check(T, "tint opacity: default 0.03, slider to 0.1, typed up to 1",
          abs(op.default - 0.03) < 1e-6 and abs(op.soft_max - 0.1) < 1e-6 and op.hard_max == 1.0)

    # a slab's far contour stays hidden behind the near cap
    for o in list(scene.objects):
        bpy.data.objects.remove(o)
    box("part-002", (30, 30, 30))
    settings(s, mode='SLICE', orientation='Z', offset=0.0, thickness=10.0)
    yield from settle()
    cam = view.rv3d.view_rotation @ Vector((0, 0, 1))
    far = min([(15, 0, -5), (-15, 0, -5), (0, 15, -5), (0, -15, -5)], key=lambda p: Vector(p).dot(cam))
    shot = Shot(view, "slab_far_contour_hidden")
    x, y = view.px(far)
    patch = [shot.at((x + dx, y + dy), r=0) for dx in range(-3, 4) for dy in range(-3, 4)]
    dark = [c for c in patch if not is_green(c)]
    check(T, "slab: far contour doesn't show through the near cap", not dark, f"{dark[:3]} at {far}")
    check(T, "no draw errors", not errors(), str(errors()))


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
        if st == 'WIREFRAME':
            info = cc("draw").last_info(view.region)
            check(T, "wireframe: still clipped, no caps or outlines",
                  view.rv3d.use_clip_planes and not info.get("count"), str(info))
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
    # every settings section opened, to see them and to run their drawing
    s.overlap_style = 'HIGHLIGHT'
    s.ui_settings = True
    for name, prop in (("cut_faces", "ui_cut_faces"), ("plane", "ui_plane"), ("measure", "ui_measure"),
                       ("print_preview", "ui_print_preview")):
        setattr(s, prop, True)
        yield 0.1
        yield from settle()
        Shot(view, f"ui_section_{name}")
        setattr(s, prop, False)
    s.ui_settings = False
    yield 0.1
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
def measure_snap(view):
    T = "measure_snap"
    dr = cc("draw")
    scene = new_scene("cc-measure-snap")
    box("part-001", (60, 40, 20))
    s = scene.crosscut
    view.look((0, 0, 0), 120, (0, 0, 0), ortho=True)
    settings(s, mode='SECTION', orientation='Z', offset=0.0)
    yield from settle()
    r = view.region
    win = view.window
    with view.override():
        bpy.ops.crosscut.measure('INVOKE_DEFAULT')
    yield 0.2
    x, y = view.px((5, -19, 0))
    win.event_simulate('MOUSEMOVE', 'NOTHING', x=r.x + x, y=r.y + y)
    yield 0.2
    win.event_simulate('LEFTMOUSE', 'PRESS', x=r.x + x, y=r.y + y)
    win.event_simulate('LEFTMOUSE', 'RELEASE', x=r.x + x, y=r.y + y)
    yield 0.2
    pin = dr._measure["anchor"]
    check(T, "anchored on the bottom edge", pin is not None and abs(pin["a"][1] + 20.0) < 0.01, str(pin and pin["a"]))
    if pin is None:
        return
    ax = float(pin["a"][0])
    # close to straight across, not quite on it
    x, y = view.px((ax + 0.3, 5, 0))
    win.event_simulate('MOUSEMOVE', 'NOTHING', x=r.x + x, y=r.y + y)
    yield 0.2
    yield from settle()
    Shot(view, "measure_snapped")
    check(T, "snaps straight across", pin["square"] is not None and abs(float(pin["b"][0]) - ax) < 1e-3
          and abs(float(pin["b"][1]) - 20.0) < 1e-3, str(pin["b"]))
    # Ctrl turns it off, without moving the mouse
    win.event_simulate('LEFT_CTRL', 'PRESS', x=r.x + x, y=r.y + y, ctrl=True)
    yield 0.2
    check(T, "Ctrl turns it off", pin["square"] is None and abs(float(pin["b"][0]) - ax) > 1e-3, str(pin["b"]))
    win.event_simulate('LEFT_CTRL', 'RELEASE', x=r.x + x, y=r.y + y)
    yield 0.2
    check(T, "and letting go turns it on", pin["square"] is not None)
    # well off the normal it doesn't snap
    x, y = view.px((ax + 15, 5, 0))
    win.event_simulate('MOUSEMOVE', 'NOTHING', x=r.x + x, y=r.y + y)
    yield 0.2
    check(T, "away from the normal it follows the cursor", pin["square"] is None)
    win.event_simulate('ESC', 'PRESS', x=r.x + x, y=r.y + y)
    win.event_simulate('ESC', 'RELEASE', x=r.x + x, y=r.y + y)
    yield 0.2
    win.event_simulate('ESC', 'PRESS', x=r.x + x, y=r.y + y)
    win.event_simulate('ESC', 'RELEASE', x=r.x + x, y=r.y + y)
    yield 0.2
    check(T, "stops", not dr.measure_running())


@test
def print_preview_580(view):
    T = "print_preview_580"
    scene = new_scene("cc-print-580")
    s = scene.crosscut
    # left half a red image, right half green: the texture has to come through the GPU sampler
    bpy.ops.mesh.primitive_cube_add(size=40, location=(0, 0, 0))
    ob = bpy.context.object
    ob.name = "part-001"
    img = bpy.data.images.new("part-001-color", 4, 4)
    img.pixels = [c for y in range(4) for x in range(4) for c in ((1, 0, 0, 1) if x < 2 else (0, 1, 0, 1))]
    img.pack()
    mat = bpy.data.materials.new("part-001-mat")
    mat.use_nodes = True
    node = mat.node_tree.nodes.new("ShaderNodeTexImage")
    node.image = img
    bsdf = next(n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
    mat.node_tree.links.new(node.outputs["Color"], bsdf.inputs["Base Color"])
    ob.data.materials.append(mat)
    me = ob.data
    uv = me.uv_layers.active  # the cube comes with one
    for loop in me.loops:
        x = me.vertices[loop.vertex_index].co.x
        uv.uv[loop.index].vector = (0.125 if x < 0 else 0.875, 0.5)
    me.update()
    # a part with a flat color, and a mirrored one: the band still has to be on the inside
    flat = box("part-002", (20, 20, 20), (50, 0, 0))
    fm = bpy.data.materials.new("part-002-mat")
    fm.use_nodes = True
    next(n for n in fm.node_tree.nodes if n.type == 'BSDF_PRINCIPLED').inputs["Base Color"].default_value = (0, 0, 1, 1)
    flat.data.materials.append(fm)
    mirrored = box("part-003", (20, 20, 20), (-50, 0, 0))
    mirrored.scale.x = -1.0
    mirrored.data.materials.append(fm)
    view.look((0, 0, 0), 150, (0, 0, 0), ortho=True)
    settings(s, mode='SECTION', orientation='Z', offset=0.0)
    s.print_preview = True
    s.print_profile = 'MJF_5600'
    yield from settle()
    plain = Shot(view, "print_preview_5600_for_580_test")
    edge_left = plain.at(view.px((-19.5, 0, 0)), r=1)
    check(T, "5600: the edge is the fused color", edge_left[0] < 60 and edge_left[1] < 60)
    s.print_profile = 'MJF_580'
    s.color_depth = 2.0
    yield from settle()
    shot = Shot(view, "print_preview_580")
    left, right = shot.at(view.px((-19.0, 0, 0)), r=1), shot.at(view.px((19.0, 0, 0)), r=1)
    check(T, "580: the texture's red on the left edge", left[0] > 128 and left[1] < 80, str(left))
    check(T, "580: the texture's green on the right edge", right[1] > 128 and right[0] < 80, str(right))
    middle = shot.at(view.px((0, 0, 0)), r=1)
    check(T, "580: the core stays fused", middle[0] < 60 and middle[1] < 60, str(middle))
    outside = shot.at(view.px((-21.5, 0, 0)), r=1)
    check(T, "580: the band stays inside the part", outside[0] > 128 and outside[1] > 128 and outside[2] > 128, str(outside))
    blue = shot.at(view.px((41.0, 0, 0)), r=1)
    check(T, "580: a flat material's color", blue[2] > 128 and blue[0] < 80, str(blue))
    blue = shot.at(view.px((-41.0, 0, 0)), r=1)
    check(T, "580: a mirrored part's band is inside too", blue[2] > 128 and blue[0] < 80, str(blue))
    outside = shot.at(view.px((-38.5, 0, 0)), r=1)
    check(T, "580: and not outside it", outside[0] > 128 and outside[1] > 128, str(outside))
    # zoomed far out, a thin band is still there
    s.color_depth = 0.01
    view.look((0, 0, 0), 1500, (0, 0, 0), ortho=True)
    yield from settle()
    far = Shot(view, "print_preview_580_far")
    px = view.px((-19.9, 0, 0))
    seen = max(far.at((px[0] + d, px[1]), r=0)[0] for d in range(0, 3))
    check(T, "580: never thinner than two pixels", seen > 100, str(seen))
    s.print_profile = 'FDM'
    yield from settle()
    fdm = Shot(view, "print_preview_fdm_placeholder")
    check(T, "FDM placeholder draws without error", not errors(), str(errors()))
    del fdm
    s.print_profile = 'MJF_5600'
    s.color_depth = 0.1
    s.print_preview = False


@test
def print_preview(view):
    T = "print_preview"
    scene = new_scene("cc-print")
    hollow_sphere("part-001", 40, 25)
    bed = box("bucket-01", (120, 120, 120))
    bed.display_type = 'WIRE'
    s = scene.crosscut
    view.look((0, 0, 0), 300, (55, 0, 30))
    settings(s, mode='SECTION', orientation='Z', offset=0.0, range_source='OBJECT', range_object=bed)
    s.print_preview = True
    yield from settle()
    shot = Shot(view, "print_preview")

    def powder(c):
        return min(c) > 195 and c[0] >= c[2]
    c = shot.at(view.px((0, -32, 0)), r=2)
    check(T, "the cut through the wall is the fused colour", max(c) < 60, f"{c}")
    c = shot.at(view.px((45, 45, 0)), r=2)
    check(T, "the bed surface is powder", powder(c), f"{c}")
    c = shot.at(view.px((0, 0, 0)), r=2)
    check(T, "powder inside the hollow part too", powder(c), f"{c}")
    c = shot.at(view.px((0, -45, -45)), r=2)
    check(T, "the part below the plane is buried (bed side or surface shows)", min(c) > 150, f"{c}")
    # a slice is one layer: the powder's surface alone, with nothing below it
    side = view.px((0, -60, -45))
    check(T, "section: the bed's side shows", min(shot.at(side, r=2)) > 120, str(shot.at(side, r=2)))
    settings(s, mode='SLICE', orientation='Z', offset=0.0, range_source='OBJECT', range_object=bed)
    s.print_preview = True
    yield from settle()
    slice_shot = Shot(view, "print_preview_slice")
    check(T, "slice: nothing below the layer", near(slice_shot.at(side, r=2), bg_of(slice_shot, view), 8),
          str(slice_shot.at(side, r=2)))
    c = slice_shot.at(view.px((45, 45, 0)), r=2)
    check(T, "slice: the layer's powder is there", powder(c), f"{c}")
    s.thickness = 20.0
    yield from settle()
    slab = Shot(view, "print_preview_slab")
    check(T, "slab: a band of powder, its side showing", min(slab.at(view.px((0, -60, -5)), r=1)) > 120
          and near(slab.at(side, r=2), bg_of(slab, view), 8), str(slab.at(view.px((0, -60, -5)), r=1)))
    settings(s, mode='SECTION', orientation='Z', offset=0.0, range_source='OBJECT', range_object=bed)
    s.print_preview = True
    yield from settle()
    lines = cc("draw").readout_lines(scene, s, cc("draw").last_info(view.region))[0]
    check(T, "readout counts layers", bool(lines) and "layer " in lines[0] and "Print Preview" in lines[0],
          str(lines))
    s.print_preview = False
    yield from settle()
    c = Shot(view, "print_preview_off").at(view.px((0, -32, 0)), r=2)
    check(T, "off again: the normal cap colour", is_green(c), f"{c}")
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
            cc("draw").forget_saved_clips()
            cc("draw").measure_clear()
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
