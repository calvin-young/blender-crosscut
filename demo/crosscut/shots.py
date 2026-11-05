# SPDX-License-Identifier: GPL-3.0-or-later
"""Crosscut reel: every segment of the video, played live in Blender.

    demo/crosscut/make.sh capture [segment ...]

Needs a Crosscut package (make.sh pins a tag) and Bucket Builder; the packed
bucket comes from cache/crosscut/packed.3mf (make.sh packs it once).
"""
import importlib
import math
import os
import sys

import bmesh
import bpy
import gpu
import numpy as np
from bpy_extras import view3d_utils
from gpu_extras.batch import batch_for_shader
from mathutils import Matrix, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path[:0] = [os.path.join(ROOT, "lib"), HERE]
import capture as C  # noqa: E402
from capture import frames, lerp, smooth, smoother, ease_out, ease_in, clamp01, orbit  # noqa: E402
import parts as P  # noqa: E402  (lib/parts.py)

OUT = os.path.join(ROOT, "cache", "crosscut", "frames")
PACKED = os.path.join(ROOT, "cache", "crosscut", "packed.3mf")
CC = "bl_ext.user_default.crosscut"
BB = "bl_ext.user_default.bucket_builder"

FLOOR = -60.0                      # bucket floor z (the demo sphere sits at the origin)
VOL = (380.0, 284.0, 380.0)        # printer volume (the packer used its lower 190 mm)
SPHERE_GREY = (0.80, 0.80, 0.80)
GEAR_ORANGE = (0.95, 0.60, 0.18)
MEASURE_TEXT = 2.2                 # mm, as hatching is in Model space
LATO_BLACK = "/usr/share/fonts/truetype/lato/Lato-Black.ttf"
MESSAGE = "CROSSCUT"
MSG_RISE = 8.0                     # mm over which the word appears, left to right: 100 layers
MSG_FULL = 2.4                     # mm of whole word above that: 30 layers
HATCH_PITCH = 1.5                  # mm, for a 50 mm part: hatching is in Model space throughout

S = {}                             # shared state between segments
KINDS = ["sphere", "demo-gear"] + [k for k, _mk, _n, _c in P.MIX]   # order of parts.write_bucket()


def cc():
    return bpy.context.scene.crosscut


def link_mesh(name, V, F, color, collection=None):
    me = bpy.data.meshes.new(name)
    me.from_pydata(np.asarray(V).tolist(), [], np.asarray(F).tolist())
    me.update()
    for p in me.polygons:
        p.use_smooth = False
    ob = bpy.data.objects.new(name, me)
    ob.color = (*color, 1.0)
    (collection or bpy.context.scene.collection).objects.link(ob)
    return ob


def centered(VF):
    V, F = VF
    V = V - 0.5 * (V.min(0) + V.max(0))
    return V, F


def _lit_font():
    for f in bpy.data.fonts:
        if f.filepath == LATO_BLACK:
            return f
    return bpy.data.fonts.load(LATO_BLACK)


def make_word():
    """The message as a part, mixed in with the build by place_word(). Its underside is a
    ramp along X, so the plane rising through it uncovers the word left to right, as
    if it were being written. The ramp only moves vertices in z and is linear in x, so
    faces stay flat and the mesh stays closed."""
    cu = bpy.data.curves.new("msg", 'FONT')
    cu.body = MESSAGE
    cu.font = _lit_font()
    cu.size = 86.0
    cu.align_x, cu.align_y = 'CENTER', 'CENTER'
    cu.extrude = 0.5
    ob = bpy.data.objects.new("msg", cu)
    bpy.context.scene.collection.objects.link(ob)
    bpy.context.view_layer.update()
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(bpy.context.evaluated_depsgraph_get()))
    bpy.data.objects.remove(ob)
    bpy.data.curves.remove(cu)
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-3)
    bm.to_mesh(me)
    bm.free()
    xs = [v.co.x for v in me.vertices]
    x0, x1 = min(xs), max(xs)
    k = min(1.0, 320.0 / (x1 - x0))      # fits the 380 mm bed
    for v in me.vertices:
        t = (v.co.x - x0) / (x1 - x0)
        z = MSG_RISE + MSG_FULL if v.co.z > 0 else MSG_RISE * t
        v.co = (v.co.x * k, v.co.y * k, z)
    me.update()
    word = bpy.data.objects.new("message", me)
    word.color = (0.25, 0.25, 0.27, 1.0)
    bpy.context.scene.collection.objects.link(word)
    return word


def place_word(word):
    """Put the word at the height where the fewest parts are in its way, in the first half
    of the build, and take those parts out of the build, so it reads cleanly among the rest."""
    bb = [word.matrix_world @ Vector(c) for c in word.bound_box]
    hx = max(abs(c.x) for c in bb) + 6.0
    hy = max(abs(c.y) for c in bb) + 6.0
    h = MSG_RISE + MSG_FULL

    def spans(ob):
        c = [ob.matrix_world @ Vector(v) for v in ob.bound_box]
        return (min(v.x for v in c), max(v.x for v in c), min(v.y for v in c), max(v.y for v in c),
                min(v.z for v in c), max(v.z for v in c))
    boxes = [(ob, spans(ob)) for ob in S["parts"]]
    keep = [spans(bpy.data.objects[n]) for n in ("hollow-sphere", "gear")]

    def in_way(b, z):
        return b[0] < hx and b[1] > -hx and b[2] < hy and b[3] > -hy and b[4] < z + h and b[5] > z

    best = None
    for mm in range(24, 56, 2):
        z = FLOOR + mm
        if any(in_way(b, z) for b in keep):
            continue
        hits = [ob for ob, b in boxes if in_way(b, z)]
        if best is None or len(hits) < len(best[1]):
            best = z, hits
    z, hits = best
    for ob in hits:
        bpy.data.objects.remove(ob)
    word.location.z = z
    bpy.context.view_layer.update()
    C.log(f"message at {z - FLOOR:.0f} mm above the floor, {len(hits)} parts taken out")
    return z


def make_problem_parts():
    """Three copies of a part: all sound for Measure, and the meshes that replace two of
    them for the mesh-check shot: a hole in the surface, and inside out."""
    def add(name, x):
        ob = link_mesh(name, *centered(P.bearing_housing()), (0.88, 0.50, 0.30))
        ob.location = (x, 0.0, 0.0)
        ob.hide_set(True)
        return ob
    housings = add("sound-part", -95.0), add("open-part", 0.0), add("inside-out-part", 95.0)
    holed = housings[1].data.copy()
    bm = bmesh.new()
    bm.from_mesh(holed)
    bm.faces.ensure_lookup_table()
    side = [f for f in bm.faces if abs(f.normal.z) < 0.2 and f.calc_center_median().y < -20.0]
    bmesh.ops.delete(bm, geom=side[:len(side) // 3], context='FACES')
    bm.to_mesh(holed)
    bm.free()
    holed.update()
    flipped = housings[2].data.copy()
    bm = bmesh.new()
    bm.from_mesh(flipped)
    bmesh.ops.reverse_faces(bm, faces=bm.faces)
    bm.to_mesh(flipped)
    bm.free()
    flipped.update()
    S["housings"] = housings
    S["bad_meshes"] = holed, flipped


# ------------------------------------------------------------------ setup

def setup():
    for m in (CC, BB):
        bpy.ops.preferences.addon_enable(module=m)
    prefs = bpy.context.preferences
    th = prefs.themes[0].view_3d
    th.face_front = (0.0, 0.0, 1.0, 0.0)             # front faces untinted...
    th.face_back = (0.85, 0.08, 0.08, 0.75)          # ...back faces red, as Blender shows them
    C.single_viewport(ui_scale=1.2)
    return 0.5


def setup_scene():
    C.configure_viewport()
    C.sidebar_first("Crosscut")
    sc = bpy.context.scene
    C.set_units_mm(sc)
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    sp = C.space()
    sp.overlay.show_face_orientation = True
    sp.overlay.grid_scale = 10.0
    sp.overlay.show_stats = False

    # the demo parts
    V, F = P.hollow_sphere()
    sphere = link_mesh("hollow-sphere", V, F, SPHERE_GREY)
    for p in sphere.data.polygons:
        p.use_smooth = True
    gear = link_mesh("gear", *centered(P.demo_gear()), GEAR_ORANGE)
    gear.rotation_euler = (math.radians(90), 0, 0)    # axis along Y, so the Y section shows its teeth
    gear.location = (130.0, 0.0, 0.0)
    gear.hide_set(True)

    # the packed bucket (hidden until it fills)
    sys.path.insert(0, os.path.expanduser("~/dev/blender-bucket-builder/bucket_builder"))
    from pack import meshio
    scene = meshio.read(PACKED)
    shift = Matrix.Translation((-0.5 * VOL[0], -0.5 * VOL[1], FLOOR))
    colors = {k: c for k, _mk, _n, c in P.MIX}
    meshes, parts = {}, []
    coll = bpy.data.collections.new("bucket")
    sc.collection.children.link(coll)
    top = FLOOR
    for it in scene.items:
        # the packer names parts part-NNN#k, numbered in the unpacked file's order
        kind = KINDS[int(it.name.split("#")[0].split("-")[1]) - 1]
        M = shift @ Matrix(np.asarray(it.matrix).tolist())
        if kind == "sphere":
            S["sphere_dest"] = M
            continue
        if kind == "demo-gear":
            # the gear object is centred and turned; work out where it must go
            V0 = it.mesh.verts
            c = 0.5 * (V0.min(0) + V0.max(0))
            S["gear_dest"] = M @ Matrix.Translation(Vector(c))
            continue
        me = meshes.get(id(it.mesh))
        if me is None:
            me = bpy.data.meshes.new(kind)
            me.from_pydata(it.mesh.verts.tolist(), [], it.mesh.tris.tolist())
            me.update()
            meshes[id(it.mesh)] = me
        ob = bpy.data.objects.new(it.name, me)
        ob.matrix_world = M
        col = colors.get(kind, (0.7, 0.7, 0.7))
        j = (hash(it.name) % 1000) / 1000.0 - 0.5          # a little variation within a family
        ob.color = (*[clamp01(x * (1 + 0.16 * j)) for x in col], 1.0)
        coll.objects.link(ob)
        parts.append(ob)
        top = max(top, max((M @ Vector(v)).z for v in ob.bound_box))
    S["parts"] = parts
    S["top"] = top
    for ob in parts:
        ob.hide_set(True)
    make_problem_parts()

    # the bed: Crosscut's scrub range and Print Preview's powder bed
    me = bpy.data.meshes.new("bucket-01")
    hz = round(top - FLOOR + 0.08, 2)       # the last layers still cut the top parts
    v = [(x, y, z) for z in (0, hz) for y in (-VOL[1] / 2, VOL[1] / 2) for x in (-VOL[0] / 2, VOL[0] / 2)]
    me.from_pydata(v, [], [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)])
    bed = bpy.data.objects.new("bucket-01", me)
    bed.location = (0, 0, FLOOR)
    bed.display_type = 'WIRE'
    sc.collection.objects.link(bed)
    bed.hide_set(True)
    S["bed"] = bed
    S["bed_h"] = hz
    C.log(f"bucket: {len(parts)} parts, top at {top:.1f}, bed {hz:.0f} mm")

    st = sc.bucket_builder
    st.detect_collisions = False
    st.monitor_volume = False
    st.volume_align = 'CENTER_XY'
    st.volume_offset = (0.0, 0.0, FLOOR)

    s = cc()
    s.mode = 'OFF'
    s.cap_style = 'BACKFACES'          # = vanilla Blender
    s.plane_display = 'NONE'
    s.hatch_space = 'MODEL'
    s.hatch_pitch = HATCH_PITCH
    s.measure_text_height = MEASURE_TEXT
    s.overlap_style = 'HIGHLIGHT'
    s.range_source = 'TARGETS'
    for ob in bpy.context.selected_objects:
        ob.select_set(False)
    P0.apply()
    return 1.0


# ------------------------------------------------------------------ poses

P0 = orbit((0, 0, 0), 205, 68, 32)                  # the sphere, three-quarter view
P1 = orbit((0, 0, 0), 195, 64, -58)                 # turned to face the cut
P2 = orbit((-3, -2, 33), 54, 50, -90)               # close on the cut wall
P3 = orbit((0, 0, 0), 215, 60, -28)                 # section planes
P4 = orbit((24, 0, 0), 235, 74, 18)                 # gear coming in
P6 = orbit((0, 0, 0), 190, 74, -10)                 # the tumbling plane ends here
P7 = orbit((34, 0, 0), 62, 88, 0)                   # close on the overlap
P8 = orbit((0, 0, 1), 108, 84, 0)                   # a housing's section, nearly face-on
P9 = orbit((47, 0, 0), 175, 84, 0)                  # a second housing sliding into it
P10 = orbit((29, 0, -5), 44, 88, 0)                 # close on their overlap
HERO = ((-30, 10, FLOOR + 26), 210, 52, 25)         # the title card's close-up


def tween(p_from, p_to, n, ease=smoother, each=None):
    for i in range(n):
        t = ease((i + 1) / n)
        p_from.lerp(p_to, t).apply()
        if each:
            each(i, t)
        yield


def hold(n):
    for _ in range(n):
        yield


# ------------------------------------------------------------------ the pointer

_mouse = {}


def _draw_pointer():
    """Screenshots don't show the mouse, and Measure is all about where it is."""
    if "xy" not in _mouse:
        return
    x, y = _mouse["xy"]
    k = 1.25
    arrow = [(0, 0), (0, -19), (4.4, -14.8), (7.5, -21.8), (10.6, -20.4), (7.6, -13.6), (13.4, -13.4)]
    pts = [(x + k * a, y + k * b) for a, b in arrow]
    tris = [(pts[0], pts[1], pts[2]), (pts[0], pts[2], pts[5]), (pts[2], pts[3], pts[4]),
            (pts[2], pts[4], pts[5]), (pts[0], pts[5], pts[6])]
    sh = gpu.shader.from_builtin('UNIFORM_COLOR')
    gpu.state.blend_set('ALPHA')
    sh.bind()
    gpu.state.line_width_set(3.0)
    sh.uniform_float("color", (0.0, 0.0, 0.0, 1.0))
    loop = [p for a, b in zip(pts, pts[1:] + pts[:1]) for p in (a, b)]
    batch_for_shader(sh, 'LINES', {"pos": loop}).draw(sh)
    gpu.state.line_width_set(1.0)
    sh.uniform_float("color", (1.0, 1.0, 1.0, 1.0))
    batch_for_shader(sh, 'TRIS', {"pos": [p for t in tris for p in t]}).draw(sh)
    gpu.state.blend_set('NONE')


def to_px(world):
    """Region pixels of a world point."""
    _a, r = C.view3d()
    return tuple(view3d_utils.location_3d_to_region_2d(r, C.rv3d(), Vector(world)))


def to_window(xy):
    _a, r = C.view3d()
    return (r.x + xy[0], r.y + xy[1])


def mouse_path(a, b, seconds, each=None, ease=smoother):
    """Glide the pointer from a to b (region pixels), hovering Measure on the way."""
    dr = importlib.import_module(CC + ".draw")
    n = frames(seconds)
    for i in range(n):
        t = ease((i + 1) / n)
        xy = (lerp(a[0], b[0], t), lerp(a[1], b[1], t))
        _mouse["xy"] = xy
        wx, wy = to_window(xy)
        with C.override():
            dr.measure_update(bpy.context, int(wx), int(wy))
        if each:
            each(i, t)
        yield


def click_at(xy):
    dr = importlib.import_module(CC + ".draw")
    wx, wy = to_window(xy)
    with C.override():
        return dr.measure_click(bpy.context, int(wx), int(wy))


# ------------------------------------------------------------------ segments

def seg_still():
    P0.apply()
    yield                                   # one frame; the edit holds it


_band = {}


def _draw_band():
    if "rect" not in _band:
        return
    x0, y0, x1, y1 = _band["rect"]
    sh = gpu.shader.from_builtin('UNIFORM_COLOR')
    pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]
    dash, gap = 10.0, 6.0
    segs = []
    for (ax, ay), (bx, by) in zip(pts, pts[1:]):
        L = math.hypot(bx - ax, by - ay)
        d = 0.0
        while d < L:
            e = min(d + dash, L)
            segs += [(ax + (bx - ax) * d / L, ay + (by - ay) * d / L), (ax + (bx - ax) * e / L, ay + (by - ay) * e / L)]
            d = e + gap
    gpu.state.blend_set('ALPHA')
    fill = [(x0, y0), (x1, y0), (x1, y1), (x0, y0), (x1, y1), (x0, y1)]
    sh.bind()
    sh.uniform_float("color", (1.0, 1.0, 1.0, 0.06))
    batch_for_shader(sh, 'TRIS', {"pos": fill}).draw(sh)
    gpu.state.line_width_set(2.0)
    sh.uniform_float("color", (0.0, 0.0, 0.0, 0.7))
    batch_for_shader(sh, 'LINES', {"pos": [(x + 1, y - 1) for x, y in segs]}).draw(sh)
    sh.uniform_float("color", (1.0, 1.0, 1.0, 0.95))
    batch_for_shader(sh, 'LINES', {"pos": segs}).draw(sh)
    gpu.state.line_width_set(1.0)
    gpu.state.blend_set('NONE')


def seg_altb():
    """Alt+B: drag a box from the sphere's middle to the lower right; the left half goes."""
    P0.apply()
    a, r = C.view3d()
    c = view3d_utils.location_3d_to_region_2d(r, C.rv3d(), Vector((0, 0, 0)))
    x0, y0 = c.x, c.y + 0.40 * r.height
    x1, y1 = c.x + 0.30 * r.width, c.y - 0.40 * r.height
    C.add_overlay(_draw_band)
    C.add_overlay(_draw_pointer)
    n = frames(0.5)
    for i in range(n):
        t = smoother((i + 1) / n)
        _mouse["xy"] = (lerp(x0 - 240, x0, t), lerp(y0 - 120, y0, t))
        yield
    n = frames(0.8)
    for i in range(n):
        t = smooth((i + 1) / n)
        _band["rect"] = (x0, y0, lerp(x0, x1, t), lerp(y0, y1, t))
        _mouse["xy"] = (lerp(x0, x1, t), lerp(y0, y1, t))
        yield
    yield from hold(6)
    with C.override():
        bpy.ops.view3d.clip_border(xmin=int(x0), xmax=int(x1), ymin=int(y1), ymax=int(y0), wait_for_input=False)
    _band.clear()
    C.remove_overlay(_draw_band)
    _mouse.clear()
    yield from hold(frames(0.6))


def seg_orbit():
    yield from tween(P0, P1, frames(3.6))


def seg_inside():
    yield from tween(P1, P2, frames(2.6))
    yield from hold(frames(0.5))


def seg_caps():
    yield from tween(P2, P1, frames(1.4))
    sp = C.space()
    sp.show_region_ui = True
    yield from hold(frames(0.5))
    cc().cap_style = 'SOLID'
    yield from hold(frames(1.0))
    cc().cap_style = 'HATCH'
    yield from hold(frames(1.2))


def seg_planes():
    s = cc()
    C.rv3d().use_clip_planes = False         # Alt+B off: Crosscut's own section plane
    s.plane_display = 'TINT'
    s.plane_opacity = 0.06
    s.mode = 'SECTION'
    s.orientation = 'X'
    s.flip = True
    s.offset = 0.0
    n = frames(5.4)
    for i in range(n):
        t = i / n
        if i == frames(1.8):
            s.orientation = 'Y'
            s.flip = True
        if i == frames(3.6):
            s.orientation = 'Z'
            s.flip = False
        s.offset = 22.0 * math.sin(2 * math.pi * (t * 3.0))
        P1.lerp(P3, smoother(t * 1.4)).apply()
        yield
    s.orientation = 'Y'
    s.flip = True
    s.offset = 0.0
    yield


def seg_any():
    """New: an Empty as the plane, tumbled through the part; then Slice with a thickness."""
    s = cc()
    sc = bpy.context.scene
    e = bpy.data.objects.new("plane", None)
    e.empty_display_type = 'SINGLE_ARROW'
    e.empty_display_size = 45.0
    sc.collection.objects.link(e)
    S["empty"] = e
    s.plane_object = e
    s.orientation = 'OBJECT'
    s.object_axis = 'Z'
    s.flip = False
    s.offset = 0.0
    n = frames(4.8)
    for i in range(n):
        t = smooth((i + 1) / n)
        e.rotation_euler = (math.radians(70 + 80 * t), math.radians(-35 + 90 * t), math.radians(40 * t))
        e.location = (0.0, -18.0 * math.sin(math.pi * t), 0.0)
        P3.lerp(P6, smoother((i + 1) / n)).apply()
        yield


def seg_slab():
    """Slice: just the cross-section, then a slab of it that thickens."""
    s = cc()
    s.mode = 'SLICE'
    s.flip = False
    s.thickness = 0.0
    yield from hold(frames(1.3))
    n = frames(2.4)
    for i in range(n):
        s.thickness = 26.0 * smoother((i + 1) / n)
        yield
    yield from hold(frames(0.5))


def seg_gear():
    s = cc()
    bpy.data.objects.remove(S.pop("empty"))
    s.plane_object = None
    s.mode = 'SECTION'
    s.orientation = 'Y'
    s.flip = True
    s.thickness = 0.0
    s.offset = 0.0
    gear = bpy.data.objects["gear"]
    gear.hide_set(False)
    gear.select_set(False)
    a = Vector((150.0, 0.0, 0.0))
    b = Vector((50.0, 0.0, 0.0))
    n = frames(2.2)
    for i in range(n):
        t = (i + 1) / n
        gear.location = a.lerp(b, ease_out(t, 3))
        P6.lerp(P4, smoother(t)).apply()
        yield
    yield from hold(frames(1.0))
    S["gear_start"] = gear.matrix_world.copy()


def seg_overlaps():
    """New: Highlight, Stripes or Blend, close on the overlap."""
    s = cc()
    yield from tween(P4, P7, frames(1.2))
    yield from hold(frames(0.6))
    s.overlap_style = 'STRIPES'
    yield from hold(frames(1.5))
    s.overlap_style = 'BLEND'
    yield from hold(frames(1.5))
    s.overlap_style = 'HIGHLIGHT'
    yield


def px(x, z):
    """Region pixels of a point on the Y section plane."""
    return to_px((x, 0.0, z))


def seg_measure():
    """New: Measure on a housing's section: hover for thickness, click to pin, click and aim.
    Its profile: bore 15, hub 26, flange 35 in x; flange -9 to -4, hub to 9 in z."""
    dr = importlib.import_module(CC + ".draw")
    s = cc()
    sp = C.space()
    bpy.data.objects["hollow-sphere"].hide_set(True)
    bpy.data.objects["gear"].hide_set(True)
    for ob in S["housings"]:
        ob.hide_set(False)
    s.plane_display = 'NONE'
    s.measure_keep = True
    sp.show_region_ui = True
    P8.apply()
    C.add_overlay(_draw_pointer)
    dr.measure_start()
    _mouse["xy"] = px(-48, 26)
    yield from hold(frames(0.3))
    # the flange: 5 mm. Pin it where it stands
    yield from mouse_path(_mouse["xy"], px(-31, -6.0), 0.9)
    yield from hold(frames(0.5))
    click_at(_mouse["xy"])
    yield from hold(frames(0.15))
    click_at(_mouse["xy"])
    yield from hold(frames(0.3))
    # along the hub wall: 11 mm. Pin that too
    yield from mouse_path(_mouse["xy"], px(-20.5, -1.0), 0.8)
    yield from mouse_path(_mouse["xy"], px(-20.5, 3.5), 0.7, ease=smooth)
    yield from hold(frames(0.2))
    click_at(_mouse["xy"])
    yield from hold(frames(0.15))
    click_at(_mouse["xy"])
    yield from hold(frames(0.3))
    # the other side: near the top, it reads the hub's height. Click the top, aim across the corner
    yield from mouse_path(_mouse["xy"], px(22.0, 7.8), 1.1)
    yield from hold(frames(0.5))
    click_at(_mouse["xy"])
    yield from hold(frames(0.2))
    yield from mouse_path(_mouse["xy"], px(17.5, -7.0), 1.0, ease=smooth)
    yield from hold(frames(0.2))
    click_at(_mouse["xy"])
    yield from hold(frames(0.3))
    yield from mouse_path(_mouse["xy"], px(48, 22), 0.6)
    _mouse.clear()
    dr.measure_stop()
    yield from hold(frames(1.4))
    dr.measure_clear()


def seg_measure_overlap():
    """New: Measure on an overlap: a second housing slides into the first."""
    dr = importlib.import_module(CC + ".draw")
    s = cc()
    right = S["housings"][2]
    yield from tween(P8, P9, frames(0.9))
    n = frames(1.3)
    for i in range(n):
        right.location.x = lerp(95.0, 58.0, ease_out((i + 1) / n, 3))
        yield
    yield from hold(frames(0.3))
    yield from tween(P9, P10, frames(1.1))
    s.measure_max = False                    # on a plain rectangle its "max" reads shorter than the width
    dr.measure_start()
    _mouse["xy"] = px(38, 3)
    yield from mouse_path(_mouse["xy"], px(26, -6.5), 1.1)
    yield from mouse_path(_mouse["xy"], px(32, -6.5), 1.2, ease=smooth)
    yield from hold(frames(1.2))
    _mouse.clear()
    C.remove_overlay(_draw_pointer)
    dr.measure_stop()
    dr.measure_clear()
    s.measure_keep = False
    s.measure_max = True
    right.location.x = 95.0


def seg_problems():
    """New: a cut says when a part's mesh isn't sound."""
    s = cc()
    sound, holed, flipped = S["housings"]
    holed.data, flipped.data = S["bad_meshes"]
    s.mode = 'SECTION'
    s.orientation = 'Y'
    s.flip = True
    s.cap_style = 'HATCH'
    s.plane_display = 'NONE'
    C.space().show_region_ui = False
    s.offset = 8.0
    PA = orbit((0, 0, -9), 262, 60, -12)
    PB = orbit((0, 0, -9), 230, 68, -4)
    n = frames(5.5)
    for i in range(n):
        t = (i + 1) / n
        PA.lerp(PB, smooth(t)).apply()
        s.offset = 8.0 - 12.0 * smooth(t)
        yield
    for ob in S.pop("housings"):
        bpy.data.objects.remove(ob)
    bpy.data.objects["hollow-sphere"].hide_set(False)
    bpy.data.objects["gear"].hide_set(False)


def seg_bucket():
    s = cc()
    s.mode = 'OFF'
    sp = C.space()
    sp.show_region_ui = False
    st = bpy.context.scene.bucket_builder
    st.monitor_volume = True
    sphere = bpy.data.objects["hollow-sphere"]
    gear = bpy.data.objects["gear"]
    s0, s1 = sphere.matrix_world.copy(), S["sphere_dest"]
    g0, g1 = gear.matrix_world.copy(), S["gear_dest"]
    parts = sorted(S["parts"], key=lambda o: o.matrix_world.translation.z)
    rng = np.random.default_rng(5)
    n_all = frames(5.0)
    start = {o: int(frames(0.8) + frames(2.6) * k / len(parts) + rng.integers(0, frames(0.35)))
             for k, o in enumerate(parts)}
    fall = frames(0.75)
    final = {o: o.matrix_world.copy() for o in parts}
    drop = {o: 160.0 + 120.0 * rng.random() for o in parts}
    PB0 = C.Pose.current()
    PB1 = orbit((0, 0, FLOOR + 80), 780, 58, -34)

    def place(M0, M1, t, lift):
        loc = M0.translation.lerp(M1.translation, t) + Vector((0, 0, lift * math.sin(math.pi * t)))
        q = M0.to_quaternion().slerp(M1.to_quaternion(), t)
        return Matrix.Translation(loc) @ q.to_matrix().to_4x4()

    for i in range(n_all):
        u = smoother(min(1.0, (i + 1) / frames(1.9)))
        PB0.lerp(PB1, u).apply()
        tm = smoother(clamp01((i - frames(0.4)) / frames(2.4)))
        sphere.matrix_world = place(s0, s1, tm, 90.0)
        gear.matrix_world = place(g0, g1, tm, 140.0)
        for o in parts:
            k = i - start[o]
            if k < 0:
                continue
            if o.hide_get():
                o.hide_set(False)
            t = min(1.0, k / fall)
            z = drop[o] * (1 - ease_in(t, 2))
            o.matrix_world = Matrix.Translation((0, 0, z)) @ final[o]
        yield
    for o in parts:
        o.matrix_world = final[o]
    yield from hold(frames(0.5))


def layer_z(k):
    return FLOOR + 0.08 * k


def seg_slice():
    """One slice through the middle of the build, on the YZ plane, then moved along X."""
    s = cc()
    bed = S["bed"]
    s.range_source = 'OBJECT'
    s.range_object = bed
    s.mode = 'SLICE'
    s.orientation = 'X'
    s.thickness = 0.0
    s.flip = False
    s.cap_style = 'SOLID'
    s.plane_display = 'NONE'
    s.overlap_style = 'BLEND'
    s.outline = True
    base = importlib.import_module(CC + ".engine").plane_base(s)
    s.offset = 0.0 - base
    PB1 = C.Pose.current()
    ctr = (0, 0, FLOOR + 42)
    PS0 = orbit(ctr, 380, 70, -62)
    PS1 = orbit(ctr, 285, 83, -86)
    n = frames(3.4)
    for i in range(n):
        t = (i + 1) / n
        if t < 0.45:
            PB1.lerp(PS0, smoother(t / 0.45)).apply()
        else:
            PS0.lerp(PS1, smooth((t - 0.45) / 0.55)).apply()
        yield
    n = frames(3.6)
    for i in range(n):
        s.offset = 62.0 * math.sin(2 * math.pi * (i + 1) / n) - base
        yield
    s.offset = -base


def seg_hero():
    """A close-up of a section through the build for the title card: not in the timeline."""
    s = cc()
    keep = s.mode, s.orientation, s.offset, s.flip, s.cap_style, s.show_readout, s.outline
    st = bpy.context.scene.bucket_builder
    st.monitor_volume = False
    S["bed"].hide_set(True)
    sp = C.space()
    sp.overlay.show_floor = False
    sp.overlay.show_axis_x = sp.overlay.show_axis_y = False
    sp.overlay.show_face_orientation = False
    sp.overlay.show_text = False
    s.show_readout = False
    s.mode = 'SECTION'
    s.orientation = 'Z'
    s.flip = False
    s.cap_style = 'HATCH'
    s.outline = True
    s.overlap_style = 'BLEND'
    s.offset = _offset_for(FLOOR + 26.0)
    pose = orbit(*HERO)
    pose.apply()
    yield 0.5
    yield
    st.monitor_volume = True
    S["bed"].hide_set(False)
    sp.overlay.show_floor = True
    sp.overlay.show_axis_x = sp.overlay.show_axis_y = True
    sp.overlay.show_face_orientation = True
    sp.overlay.show_text = True
    s.mode, s.orientation, s.offset, s.flip, s.cap_style, s.show_readout, s.outline = keep


def _offset_for(z):
    """Crosscut's offset for a plane at height z (orientation Z)."""
    return z - importlib.import_module(CC + ".engine").plane_base(cc())


def print_setup():
    s = cc()
    sp = C.space()
    word = make_word()
    bpy.context.view_layer.update()
    S["word_k"] = int(round((place_word(word) - FLOOR) / 0.08))
    s.mode = 'SECTION'
    s.orientation = 'Z'
    s.flip = False
    s.step = 0.08
    S["n_layers"] = int(round(S["bed_h"] / 0.08))
    sp.overlay.show_floor = False
    sp.overlay.show_axis_x = sp.overlay.show_axis_y = False
    s.ui_settings = True
    s.ui_print_preview = True


def set_layer(k):
    cc().offset = _offset_for(layer_z(k) + 0.04)


def seg_print():
    """Print Preview: the bed from an angle, rising to about a third of the build."""
    s = cc()
    sp = C.space()
    print_setup()
    ctr = Vector((0, 0, FLOOR))
    set_layer(0)
    PO0 = orbit(ctr + Vector((0, 0, 30)), 560, 58, -12, ortho=True)
    PO0.apply()
    sp.show_region_ui = True
    yield from hold(frames(0.5))
    s.print_preview = True
    yield from hold(frames(0.8))
    S["k"] = 0
    k1 = int(S["word_k"] * 0.34)
    PO_mid = orbit(ctr + Vector((0, 0, 45)), 520, 46, 40, ortho=True)
    n = frames(4.0)
    for i in range(n):
        t = (i + 1) / n
        set_layer(int(round(k1 * smooth(t))))
        PO0.lerp(PO_mid, smoother(t)).apply()
        if i == frames(2.5):
            sp.show_region_ui = False
        yield
    S["k"] = k1
    S["pose"] = PO_mid


def seg_top():
    """The dwell: straight down, layer after layer."""
    ctr = Vector((0, 0, FLOOR))
    hz = S["bed_h"]
    PO_top = orbit(ctr + Vector((0, 0, hz)), 425, 0, 0, ortho=True)
    k0, k1 = S["k"], S["word_k"]
    n = frames(7.0)
    for i in range(n):
        t = (i + 1) / n
        set_layer(int(round(lerp(k0, k1, min(1.0, t)))))
        S["pose"].lerp(PO_top, smoother(t / 0.3)).apply()
        yield
    S["k"] = k1
    PO_top.apply()


def seg_word():
    """The layers write the message, among the parts."""
    k0 = S["k"]
    rise = int(MSG_RISE / 0.08)
    for k in range(k0, k0 + rise):
        set_layer(k)
        yield
    for k in range(k0 + rise, k0 + int((MSG_RISE + MSG_FULL) / 0.08)):   # slower: time to read it
        set_layer(k)
        yield
        yield
    yield from hold(frames(0.6))


SEGMENTS = [
    ("a_still", seg_still),
    ("b_altb", seg_altb),
    ("c_orbit", seg_orbit),
    ("d_inside", seg_inside),
    ("e_caps", seg_caps),
    ("f_planes", seg_planes),
    ("f2_any", seg_any),
    ("f3_slab", seg_slab),
    ("g_gear", seg_gear),
    ("g2_overlaps", seg_overlaps),
    ("g3_measure", seg_measure),
    ("g4_overlap", seg_measure_overlap),
    ("g5_problems", seg_problems),
    ("h_bucket", seg_bucket),
    ("i_slice", seg_slice),
    ("z_hero", seg_hero),
    ("j_print", seg_print),
    ("k_top", seg_top),
    ("l_word", seg_word),
]

if __name__ == "__main__":
    only = set(C.args()) or None
    C.Reel(OUT, SEGMENTS, setup=[setup, setup_scene]).start(only)
