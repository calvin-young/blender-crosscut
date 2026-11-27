# SPDX-License-Identifier: GPL-3.0-or-later
"""A small public API for other add-ons (D-054).

Found without importing Crosscut:

    api = bpy.app.driver_namespace.get("crosscut")
    if api and api.API_VERSION >= 1:
        api.set_section(z, owner="my_addon")

A caller owns the section it sets. It may move it as often as it likes and must
clear it when done; clearing puts back the user's own settings from before. A
section the user made, or took over (turned off, changed mode or axis), is never
touched: set_section and set_slab return False instead, unless force=True.
"""

import json

import bpy
import numpy as np

from . import engine

API_VERSION = 1
KEY = "crosscut"

# what a caller's section changes, saved before and put back on clear
_SAVED = ("view_normal", "view_base", "orientation", "offset", "thickness", "flip", "placed",
          "targets", "target_collection", "last_mode", "mode")  # mode last: it pushes the planes


def _settings(scene):
    s = getattr(scene or bpy.context.scene, "crosscut", None)
    if s is None:
        raise RuntimeError("Crosscut is not registered")
    return s


def _record(s):
    try:
        return json.loads(s.api_record) if s.api_record else None
    except ValueError:
        return None


def _signature(s):
    return [s.mode, s.orientation, [round(v, 6) for v in s.view_normal]]


def _owner(s):
    """The add-on whose section is showing, or "" when it's the user's or none."""
    rec = _record(s)
    if rec is None or rec.get("signature") != _signature(s):
        return ""
    return rec.get("owner", "")


def _user_clip_region():
    from . import draw
    for _win, _area, _region, rv3d in draw._iter_views():
        if rv3d.use_clip_planes:
            return True
    return False


def section_info(scene=None):
    """None when nothing is clipped, else a dict:
    mode ('SECTION', 'SLICE' or 'CLIP' for the user's clipping region), owner (the
    add-on that set it, "" for the user), normal, offset (the plane's position along
    the normal) and thickness (Slice only)."""
    s = _settings(scene)
    if s.mode == 'OFF':
        return {"mode": 'CLIP', "owner": ""} if _user_clip_region() else None
    f = engine.plane_frame(s)
    if f is None:
        return None
    n, base = f
    return {"mode": s.mode, "owner": _owner(s), "normal": tuple(float(v) for v in n),
            "offset": float(base + s.offset), "thickness": float(s.thickness) if s.mode == 'SLICE' else 0.0}


def _place(s, mode, c, normal, thickness, collection, owner, force):
    if not owner:
        raise ValueError("owner is required: the caller's add-on name")
    info = section_info(s.id_data)
    if info is not None and info["owner"] != owner and not force:
        return False
    n = np.array(normal, dtype=np.float64)
    if n.shape != (3,) or np.linalg.norm(n) < 1e-12:
        raise ValueError("normal must be a non-zero 3-vector")
    n = n / np.linalg.norm(n)
    if _owner(s) != owner:  # first call: remember the user's settings
        saved = {}
        for k in _SAVED:
            v = getattr(s, k)
            saved[k] = (v.name if v else None) if k == "target_collection" else (
                list(v) if k == "view_normal" else v)
        rec = {"owner": owner, "saved": saved}
    else:
        rec = _record(s)
    axis = next((a for a, v in engine.AXES.items() if abs(abs(float(n @ v)) - 1.0) < 1e-9), None)
    if axis is not None:
        sign = float(n @ engine.AXES[axis])
        s.orientation = axis
        s.offset = c * sign
        s.flip = sign < 0
    else:
        s.view_normal = n
        s.view_base = 0.0
        s.orientation = 'VIEW'
        s.offset = c
        s.flip = False
    if mode == 'SLICE':
        s.thickness = thickness
    if collection is not None:
        s.target_collection = collection
        s.targets = 'COLLECTION'
    s.placed = True
    s.mode = mode
    s.last_mode = mode
    rec["signature"] = _signature(s)
    s.api_record = json.dumps(rec)
    return True


def set_section(z, normal=(0.0, 0.0, 1.0), collection=None, owner="", force=False, scene=None):
    """Show a section at offset z along normal (scene units; for the default normal,
    the height z), keeping the side below, i.e. against the normal. collection limits
    the filled cut faces to its objects (everything is still clipped). Returns False,
    changing nothing, when the user's own section or clipping region is showing."""
    s = _settings(scene)
    return _place(s, 'SECTION', float(z), normal, 0.0, collection, owner, force)


def set_slab(z0, z1, normal=(0.0, 0.0, 1.0), collection=None, owner="", force=False, scene=None):
    """Show only what lies between offsets z0 and z1 along normal (Slice mode).
    z0 == z1 shows the cross-section alone."""
    s = _settings(scene)
    lo, hi = sorted((float(z0), float(z1)))
    return _place(s, 'SLICE', (lo + hi) / 2, normal, hi - lo, collection, owner, force)


def clear_section(owner, scene=None):
    """Remove the owner's section and put back the user's settings from before.
    Returns False, changing nothing, when the section showing isn't the owner's."""
    s = _settings(scene)
    rec = _record(s)
    if rec is None or rec.get("owner") != owner:
        return False
    mine = _owner(s) == owner
    s.api_record = ""
    if not mine:  # the user took it over: theirs now, leave it be
        return False
    for k, v in rec["saved"].items():
        if k == "target_collection":
            v = bpy.data.collections.get(v) if v else None
        try:
            setattr(s, k, v)
        except (TypeError, ValueError, AttributeError):
            pass
    return True


def register():
    import sys
    bpy.app.driver_namespace[KEY] = sys.modules[__name__]


def unregister():
    if bpy.app.driver_namespace.get(KEY) is not None:
        del bpy.app.driver_namespace[KEY]
