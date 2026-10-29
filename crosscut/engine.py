# SPDX-License-Identifier: GPL-3.0-or-later
"""Plane bookkeeping, target collection and cached section computation."""

import bpy
import numpy as np

from . import section_math as sm

TARGET_TYPES = {'MESH', 'CURVE', 'SURFACE', 'FONT', 'META'}
AXES = {'X': (1.0, 0.0, 0.0), 'Y': (0.0, 1.0, 0.0), 'Z': (0.0, 0.0, 1.0)}



# ------------------------------------------------------------------ the plane

def plane_frame(s):
    """(unit normal, base) where the plane is  dot(n, p) = base + s.offset.
    None when the plane is undefined (Object orientation with no object)."""
    if s.orientation in AXES:
        return np.array(AXES[s.orientation]), 0.0
    if s.orientation == 'VIEW':
        n = np.array(s.view_normal, dtype=np.float64)
        if np.linalg.norm(n) < 1e-12:
            return None
        return sm.normalize(n), float(s.view_base)
    ob = s.plane_object
    if ob is None:
        return None
    m = np.array(ob.matrix_world)
    z = m[:3, 2]
    if np.linalg.norm(z) < 1e-12:
        return None
    n = sm.normalize(z)
    return n, float(n @ m[:3, 3])


def plane_base(s):
    f = plane_frame(s)
    return None if f is None else f[1]


def plane_coordinate(s):
    f = plane_frame(s)
    return None if f is None else f[1] + s.offset


def compute_planes(s):
    """Return (clip_planes, caps) for the current settings, or None if inactive.

    clip_planes: list (<= 6) of 4-vectors for RegionView3D.clip_planes.
    caps: list of (plane, bound_planes); a cap is drawn on `plane`, limited by
    the other active planes.
    """
    if s.mode == 'OFF':
        return None
    f = plane_frame(s)
    if f is None:
        return None
    n, base = f
    c = base + s.offset
    if s.mode == 'SECTION':
        keep = np.concatenate([-n, [c]])  # keep n.p <= c
        if s.flip:
            keep = -keep
        return [keep], [(keep, [])]
    # SLICE
    t = s.thickness
    if t <= 1e-9:
        cap = np.concatenate([n, [-c]])
        return [np.array(sm.CLIP_ALL)], [(cap, [])]
    lo = np.concatenate([n, [-(c - t / 2)]])   # keep n.p >= c - t/2
    hi = np.concatenate([-n, [c + t / 2]])     # keep n.p <= c + t/2
    return [lo, hi], [(lo, [hi]), (hi, [lo])]


def native_caps(rv3d):
    """Caps for Blender's own Alt+B clipping region."""
    planes = [np.array(p, dtype=np.float64) for p in rv3d.clip_planes]
    out = []
    for i, p in enumerate(planes):
        if sm.plane_is_degenerate(p):
            continue
        others = [q for j, q in enumerate(planes) if j != i]
        out.append((p, others))
    return out


# ---------------------------------------------------------------- targets

def is_flat(ob):
    """A plane-like mesh (one bounding-box side ~0): a cutter, not a part."""
    dims = np.ptp(np.array([tuple(c) for c in ob.bound_box], dtype=np.float64), axis=0)
    return float(dims.min()) <= 1e-6 * max(float(dims.max()), 1e-12)


def is_helper(ob, s):
    if ob is None:
        return False
    if ob == s.range_object:
        return True
    if ob == s.plane_object and is_flat(ob):
        return True  # a plane mesh used as the cutter; a part used as its own plane is still capped
    return ob.display_type in {'WIRE', 'BOUNDS'}


def obvious_plane_object(context):
    """The only visible Empty, else the only visible object, else None."""
    view_layer = context.view_layer
    if view_layer is None:
        return None
    vis = [ob for ob in view_layer.objects if ob is not None and _visible(ob, view_layer, None)
           and ob.type not in {'CAMERA', 'LIGHT', 'LIGHT_PROBE', 'SPEAKER'}]
    empties = [ob for ob in vis if ob.type == 'EMPTY']
    if len(empties) == 1:
        return empties[0]
    if not empties and len(vis) == 1:
        return vis[0]
    return None


def hidden_from_caps(context, s):
    """Visible solids not capped because they display as Wire or Bounds
    (the range object is left out: it's meant to be uncapped)."""
    view_layer = context.view_layer
    if view_layer is None:
        return []
    return [ob.name for ob in view_layer.objects
            if ob is not None and ob.type in TARGET_TYPES and ob.display_type in {'WIRE', 'BOUNDS'}
            and ob != s.range_object and _visible(ob, view_layer, None)]


def _visible(ob, view_layer, space):
    try:
        return ob.visible_get(view_layer=view_layer, viewport=space)
    except (TypeError, RuntimeError):
        try:
            return ob.visible_get()
        except RuntimeError:
            return False


def original_targets(context, s):
    """Original (non-evaluated) target objects; used for scrub ranges and
    simple counts. Instances are not expanded here."""
    view_layer = context.view_layer
    if view_layer is None:
        return []
    coll = None
    if s.targets == 'COLLECTION' and s.target_collection is not None:
        coll = set(s.target_collection.all_objects)
    out = []
    for ob in view_layer.objects:
        if ob is None or ob.type not in TARGET_TYPES or is_helper(ob, s):
            continue
        if not _visible(ob, view_layer, None):
            continue
        if s.targets == 'SELECTED' and not ob.select_get(view_layer=view_layer):
            continue
        if coll is not None and ob not in coll:
            continue
        out.append(ob)
    return out


def _corners(ob):
    m = np.array(ob.matrix_world)
    bb = np.array([tuple(c) for c in ob.bound_box], dtype=np.float64)
    return sm.transform_points(bb, m)


def scrub_range(s):
    """(lo, hi) of the plane coordinate across the scrub range."""
    f = plane_frame(s)
    if f is None:
        return 0.0, 0.0
    n = f[0]
    if s.range_source == 'OBJECT' and s.range_object is not None:
        obs = [s.range_object]
    else:
        obs = original_targets(bpy.context, s)
    if not obs:
        return 0.0, 0.0
    pts = np.concatenate([_corners(o) for o in obs])
    return sm.project_range(pts, n)


def center_offset(s):
    """Offset that puts the plane through the middle of the scrub range."""
    lo, hi = scrub_range(s)
    base = plane_base(s)
    if base is None or hi <= lo:
        return s.offset
    return 0.5 * (lo + hi) - base


def target_points(context, s):
    obs = original_targets(context, s)
    if not obs:
        return np.zeros((0, 3))
    return np.concatenate([_corners(o) for o in obs])


class Target:
    __slots__ = ("key", "mesh_key", "eval_ob", "matrix", "orig", "owner")

    def __init__(self, key, mesh_key, eval_ob, matrix, orig, owner):
        self.key = key
        self.mesh_key = mesh_key
        self.eval_ob = eval_ob
        self.matrix = matrix
        self.orig = orig
        self.owner = owner


def collect_targets(context, s, depsgraph):
    view_layer = context.view_layer
    space = context.space_data
    coll = None
    if s.targets == 'COLLECTION':
        if s.target_collection is None:
            return []
        coll = set(s.target_collection.all_objects)
    out = []
    for inst in depsgraph.object_instances:
        ob = inst.object
        if ob is None or ob.type not in TARGET_TYPES:
            continue
        orig = ob.original
        is_inst = inst.is_instance
        owner = inst.parent.original if (is_inst and inst.parent is not None) else orig
        if not _visible(owner, view_layer, space):
            continue
        if is_helper(orig, s) or is_helper(owner, s):
            continue
        if s.targets == 'SELECTED' and not owner.select_get(view_layer=view_layer):
            continue
        if coll is not None and owner not in coll and orig not in coll:
            continue
        pid = tuple(inst.persistent_id) if is_inst else ()
        data_name = ob.data.name_full if ob.data is not None else ""
        key = (orig.name_full, is_inst, pid)
        mesh_key = (orig.name_full, data_name, is_inst)
        out.append(Target(key, mesh_key, ob, np.array(inst.matrix_world), orig, owner))
    out.sort(key=lambda t: (t.owner.name_full, t.key))
    return out


# ----------------------------------------------------------------- caches

_meshes = {}        # mesh_key -> dict(v, t, bbmin, bbmax, ver), or False for "no geometry"
_sections = {}      # (target key, cap index) -> (signature, result)
_version = [0]


def invalidate_object(name):
    for mk in [mk for mk in _meshes if mk[0] == name]:
        del _meshes[mk]


def invalidate_all():
    _meshes.clear()
    _sections.clear()


def _mesh(target, depsgraph):
    mk = target.mesh_key
    e = _meshes.get(mk)
    if e is not None:
        return e or None
    ob = target.eval_ob
    me = None
    try:
        me = ob.to_mesh(preserve_all_data_layers=False, depsgraph=depsgraph)
    except (RuntimeError, TypeError):
        try:
            me = ob.to_mesh()
        except RuntimeError:
            me = None
    e = False
    if me is not None:
        if hasattr(me, "calc_loop_triangles"):
            me.calc_loop_triangles()
        nv = len(me.vertices)
        nt = len(me.loop_triangles)
        v = np.empty(nv * 3, dtype=np.float32)
        t = np.empty(nt * 3, dtype=np.int32)
        if nv:
            me.vertices.foreach_get("co", v)
        if nt:
            me.loop_triangles.foreach_get("vertices", t)
        try:
            ob.to_mesh_clear()
        except RuntimeError:
            pass
        if nv and nt:
            v = v.reshape(-1, 3).astype(np.float64)
            t = t.reshape(-1, 3).astype(np.int64)
            _version[0] += 1
            cols = tuple(np.ascontiguousarray(t[:, i]) for i in range(3))
            e = dict(v=v, t=t, cols=cols, bbmin=v.min(0), bbmax=v.max(0), ver=_version[0])
    _meshes[mk] = e
    return e or None


def _cap_misses(e, m, plane, bounds):
    """True when the part of the plane inside the other planes (`bounds`)
    cannot touch the target's bounding box, so there is nothing to cap."""
    if not len(bounds):
        return False
    corners = np.array([[x, y, z] for x in (e["bbmin"][0], e["bbmax"][0])
                        for y in (e["bbmin"][1], e["bbmax"][1])
                        for z in (e["bbmin"][2], e["bbmax"][2])])
    w = sm.transform_points(corners, m)
    poly = sm.box_section_polygon(plane, w.min(0), w.max(0))
    return len(poly) == 0 or len(sm.clip_convex_polygon(poly, bounds)) == 0


def section(target, cap_index, plane, depsgraph, bounds=()):
    """(segments (K,2,3) world space, open-endpoint count, serial) for one
    target, or None. `serial` changes whenever the segments change. Targets
    whose cut lies wholly outside the other active planes (`bounds`) are
    skipped: with Alt+B's six planes most of them are."""
    e = _mesh(target, depsgraph)
    if e is None:
        return None
    m = target.matrix
    sig = (e["ver"], m.tobytes(), np.asarray(plane, dtype=np.float64).tobytes(),
           np.asarray(bounds, dtype=np.float64).tobytes())
    ck = (target.key, cap_index)
    hit = _sections.get(ck)
    if hit is not None and hit[0] == sig:
        return hit[1]
    local = sm.plane_to_local(plane, m)
    if not sm.bbox_crosses_plane(e["bbmin"], e["bbmax"], local) or _cap_misses(e, m, plane, bounds):
        res = None
    else:
        seg = sm.section_segments(e["v"], e["t"], local, e["cols"])
        if len(seg) == 0:
            res = None
        else:
            seg_w = sm.transform_points(seg.reshape(-1, 3), m).reshape(-1, 2, 3)
            _version[0] += 1
            res = (seg_w, sm.open_endpoint_count(seg), _version[0])
    _sections[ck] = (sig, res)
    return res


def objects_at(context, s, point, plane, depsgraph):
    """Owners of the targets whose section on `plane` (cap index 0, as drawn)
    contains the world point, in target order. Even-odd test in the plane."""
    u, v = sm.plane_basis(sm.normalize(plane[:3]))
    px, py = float(point @ u), float(point @ v)
    out = []
    for t in collect_targets(context, s, depsgraph):
        res = section(t, 0, plane, depsgraph)
        if res is None:
            continue
        seg = res[0]
        ax, ay = seg[:, 0] @ u, seg[:, 0] @ v
        bx, by = seg[:, 1] @ u, seg[:, 1] @ v
        crosses = (ay > py) != (by > py)
        with np.errstate(divide='ignore', invalid='ignore'):
            x_at = ax + (py - ay) * (bx - ax) / (by - ay)
        if int(np.count_nonzero(crosses & (px < x_at))) % 2 == 1 and t.owner not in out:
            out.append(t.owner)
    return out


def prune(live_keys):
    """Drop cached sections for targets that no longer exist."""
    for k in [k for k in _sections if k[0] not in live_keys]:
        del _sections[k]


# ---------------------------------------------------------------- handlers

def on_depsgraph_update(_scene, depsgraph):
    plane_moved = False
    for up in depsgraph.updates:
        idb = up.id
        if isinstance(idb, bpy.types.Object):
            if up.is_updated_geometry:
                invalidate_object(idb.original.name_full)
            if up.is_updated_transform:
                plane_moved = True
        elif isinstance(idb, (bpy.types.Mesh, bpy.types.Curve, bpy.types.MetaBall)):
            orig = idb.original
            for ob in bpy.data.objects:
                if ob.data == orig:
                    invalidate_object(ob.name_full)
    if plane_moved:
        # an Object plane (or a range object) may have moved: update the clip
        # planes before the next redraw instead of one frame late
        from . import draw
        try:
            draw.sync_views()
        except Exception as ex:  # noqa: BLE001 - the draw callback retries and reports
            print("Crosscut: sync failed:", ex)


def on_load(*_args):
    invalidate_all()
