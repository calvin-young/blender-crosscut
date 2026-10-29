# SPDX-License-Identifier: GPL-3.0-or-later
"""Logic tests for the add-on modules with bpy/gpu stubbed out.

These do not exercise drawing; they check plane bookkeeping and the
clip-plane hand-off state machine. Real viewport behaviour is covered by
tools/showcase.py inside Blender.
"""

import os
import sys
import types

import numpy as np

ROOT = os.path.join(os.path.dirname(__file__), "..")


# ----------------------------------------------------------------- stubs

def _install_stubs():
    if "bpy" in sys.modules and getattr(sys.modules["bpy"], "_crosscut_stub", False):
        return
    bpy = types.ModuleType("bpy")
    bpy._crosscut_stub = True

    class _Base:
        pass

    bpy.types = types.SimpleNamespace(
        Operator=_Base, Panel=_Base, Menu=_Base, PropertyGroup=_Base,
        Object=type("Object", (), {}), Collection=type("Collection", (), {}),
        Mesh=type("Mesh", (), {}), Curve=type("Curve", (), {}), MetaBall=type("MetaBall", (), {}),
        Scene=type("Scene", (), {}), SpaceView3D=_Base, VIEW3D_HT_header=_Base,
    )
    props = types.ModuleType("bpy.props")
    for name in ("BoolProperty", "EnumProperty", "FloatProperty", "FloatVectorProperty",
                 "IntProperty", "PointerProperty", "StringProperty"):
        setattr(props, name, lambda *a, **k: None)
    bpy.props = props
    timers = []
    bpy.app = types.SimpleNamespace(
        timers=types.SimpleNamespace(register=lambda fn, first_interval=0.0: timers.append(fn)),
        handlers=types.SimpleNamespace(persistent=lambda f: f, depsgraph_update_post=[],
                                       load_post=[], undo_post=[], redo_post=[]),
    )
    bpy._timers = timers
    bpy.context = types.SimpleNamespace(window_manager=None)
    bpy.utils = types.SimpleNamespace(register_class=lambda c: None, unregister_class=lambda c: None)
    handlers_mod = types.ModuleType("bpy.app.handlers")
    handlers_mod.persistent = lambda f: f
    sys.modules["bpy"] = bpy
    sys.modules["bpy.props"] = props
    sys.modules["bpy.app"] = bpy.app
    sys.modules["bpy.app.handlers"] = handlers_mod

    for name in ("gpu", "blf"):
        sys.modules[name] = types.ModuleType(name)
    ge = types.ModuleType("gpu_extras")
    geb = types.ModuleType("gpu_extras.batch")
    geb.batch_for_shader = lambda *a, **k: None
    sys.modules["gpu_extras"] = ge
    sys.modules["gpu_extras.batch"] = geb
    mu = types.ModuleType("mathutils")
    mu.Matrix = object
    mu.Vector = object
    sys.modules["mathutils"] = mu


_install_stubs()
sys.path.insert(0, ROOT)
from crosscut import draw, engine  # noqa: E402
from crosscut import section_math as sm  # noqa: E402


def settings(**kw):
    d = dict(mode='SECTION', orientation='Z', plane_object=None, offset=0.0, flip=False,
             thickness=0.0, range_source='TARGETS', range_object=None)
    d.update(kw)
    return types.SimpleNamespace(**d)


def kept(plane, p):
    return np.dot(plane[:3], p) + plane[3] >= 0


# ----------------------------------------------------------------- planes

def test_section_keeps_below_plane_and_flip_keeps_above():
    clip, caps = engine.compute_planes(settings(offset=5.0))
    assert kept(clip[0], [0, 0, 4]) and not kept(clip[0], [0, 0, 6])
    clip, _ = engine.compute_planes(settings(offset=5.0, flip=True))
    assert kept(clip[0], [0, 0, 6]) and not kept(clip[0], [0, 0, 4])
    assert len(caps) == 1


def test_slice_slab_and_section_only():
    clip, caps = engine.compute_planes(settings(mode='SLICE', orientation='X', offset=5.0, thickness=2.0))
    for x, want in ((3.9, False), (4.1, True), (5.9, True), (6.1, False)):
        assert all(kept(c, [x, 0, 0]) for c in clip) == want, x
    assert len(caps) == 2
    clip, caps = engine.compute_planes(settings(mode='SLICE', offset=5.0, thickness=0.0))
    assert not kept(clip[0], [0, 0, 5])  # everything clipped, only the cap is drawn
    assert np.isclose(np.dot(caps[0][0][:3], [0, 0, 5]) + caps[0][0][3], 0.0)


def test_off_and_missing_object():
    assert engine.compute_planes(settings(mode='OFF')) is None
    assert engine.compute_planes(settings(orientation='OBJECT')) is None


def test_object_plane_uses_local_z_and_origin():
    m = np.eye(4)
    m[:3, :3] = [[1, 0, 0], [0, 0, -1], [0, 1, 0]]  # local Z -> world -Y... rows are basis
    m[:3, 3] = [0, 10, 0]
    ob = types.SimpleNamespace(matrix_world=m)
    n, base = engine.plane_frame(settings(orientation='OBJECT', plane_object=ob))
    assert np.allclose(n, m[:3, 2] / np.linalg.norm(m[:3, 2]))
    assert np.isclose(base, n @ m[:3, 3])


# --------------------------------------------------------- clip hand-off

class FakeRV3D:
    def __init__(self, on=False, planes=None):
        self.use_clip_planes = on
        self.clip_planes = planes or [[0.0, 0.0, 0.0, 0.0]] * 6

    def as_pointer(self):
        return id(self)


def _planes_of(r):
    return np.array(r.clip_planes, dtype=np.float64)


def test_take_over_and_release_leaves_no_clipping():
    user_box = [[1.0, 0, 0, 5]] + [[0.0, 0, 0, 1]] * 5
    r = FakeRV3D(on=True, planes=[list(p) for p in user_box])
    want = [np.array([0, 0, -1.0, 3.0])]
    assert draw.sync_clip(r, want) is True
    assert r.use_clip_planes and np.allclose(_planes_of(r)[0], want[0])
    assert draw.sync_clip(r, want) is True  # stable
    assert draw.sync_clip(r, None) is False  # release: no clipping, not the old Alt+B box
    assert not r.use_clip_planes


def test_user_alt_b_turns_crosscut_off():
    import bpy
    r = FakeRV3D()
    want = [np.array([0, 0, -1.0, 3.0])]
    draw.sync_clip(r, want)
    r.use_clip_planes = False  # Alt+B with clipping active toggles it off
    n_timers = len(bpy._timers)
    assert draw.sync_clip(r, want) is False
    assert len(bpy._timers) == n_timers + 1  # deferred mode -> OFF
    assert r.use_clip_planes is False  # and we did not fight the user


def test_moving_plane_updates_without_triggering_hand_off():
    r = FakeRV3D()
    draw.sync_clip(r, [np.array([0, 0, -1.0, 3.0])])
    assert draw.sync_clip(r, [np.array([0, 0, -1.0, 3.5])]) is True
    assert np.isclose(_planes_of(r)[0][3], 3.5)


def test_unused_slots_clip_nothing():
    r = FakeRV3D()
    draw.sync_clip(r, [np.array([0, 0, -1.0, 3.0])])
    for p in _planes_of(r)[1:]:
        assert kept(p, [1e6, -1e6, 1e6])
    assert sm.CLIP_NONE[3] > 0


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
