# SPDX-License-Identifier: GPL-3.0-or-later
"""Viewport drawing: clip-plane sync, GPU cap rendering, outlines and readout.

How the caps are drawn (no stencil buffer, no triangulation)
-------------------------------------------------------------
For every target and cap plane, the mesh is intersected with the plane on the
CPU (numpy, cached) which gives a bag of line segments. Each segment becomes a
fan triangle (apex, a, b). Those triangles are rasterized into an offscreen
mask with *invert* blending, so a pixel flips every time it is covered: it ends
up lit exactly when it lies inside the closed cross-section (even-odd rule).
Holes, multiple islands and nested shells come out right for free.

A quad on the plane (clipped to the other active planes) is then drawn into the
viewport with the scene's depth buffer; its fragment shader keeps only lit mask
pixels and paints the fill and hatching. Where two or more objects' masks
overlap, an interference pass paints red cross-hatching on top.
"""

import math

import blf
import bpy
import gpu
import numpy as np
from gpu_extras.batch import batch_for_shader
from mathutils import Matrix, Vector

from . import engine
from . import section_math as sm

_handles = []
_shaders = {}
_offscreens = {}
_batches = {}          # (target key, cap index, kind) -> (signature, batch)
_clip_state = {}       # rv3d pointer -> {"ours": flat planes or None, "saved": (on, planes)}
_errors = set()
_last_info = {}        # per-region info for the readout
_clip_lit = {}         # rv3d pointer -> whether the sidebar's Clip button should be lit
_tint_gone = set()     # rv3d pointers whose clipping region has had Blender's tinted box removed
_tint_pending = set()
_tool_box = {}         # rv3d pointer -> the planes its clipping box was last fitted for
_tool_box_pending = set()
_saved_clip = {}       # rv3d pointer -> the clipping region's planes when Section or Slice took over
_measure = {"on": False, "region": None, "a": None, "b": None, "text": "", "la": None, "lb": None, "ltext": "",
            "cut": None, "anchor": None, "dims": []}  # hover lines, the line being placed, pinned lines


# ------------------------------------------------------------------ shaders

_MASK_VS = """
void main() {
    gl_Position = viewProj * vec4(pos, 1.0);
}
"""
_MASK_FS = """
void main() {
    fragColor = vec4(1.0);
}
"""
_WIND_FS = """
void main() {
    fragColor = windColor;
}
"""
_RESOLVE_FS = """
void main() {
    vec2 w = texelFetch(maskTex, ivec2(gl_FragCoord.xy), 0).rg;
    if (abs(w.r - w.g) < 0.5 / 255.0) {
        discard;
    }
    fragColor = vec4(1.0);
}
"""
_ACCUM_VS = """
void main() {
    gl_Position = vec4(pos, 0.0, 1.0);
}
"""
_ACCUM_FS = """
void main() {
    float m = texelFetch(maskTex, ivec2(gl_FragCoord.xy), 0).r;
    if (m < 0.5) {
        discard;
    }
    fragColor = vec4(COUNT_STEP, 0.0, 0.0, 1.0);
}
"""
_CAP_VS = """
void main() {
    vUV = uv;
    gl_Position = viewProj * vec4(pos, 1.0);
    gl_Position.z -= depthBias * gl_Position.w;
}
"""
_CAP_FS = """
float hatch_line(float x, float pitch, float width) {
    float f = x / pitch;
    float aa = max(0.5 * fwidth(f), 1e-4);  // about one pixel of antialiasing
    float d = abs(fract(f + 0.5) - 0.5);
    return 1.0 - smoothstep(width * 0.5 - aa, width * 0.5 + aa, d);
}

void main() {
    float m = texelFetch(maskTex, ivec2(gl_FragCoord.xy), 0).r;
    if (threshold > 1.5) {
        // inverted: keep only where the mask is NOT lit
        if (m > 0.5) {
            discard;
        }
    }
    else if (m < threshold) {
        discard;
    }
    vec4 col = fillColor;
    if (hatch.w > 0.5) {
        vec2 p = (hatch.x < 0.0) ? gl_FragCoord.xy : vUV;
        float pitch = abs(hatch.x);
        vec2 d = vec2(hatch.y, hatch.z);
        float l = hatch_line(dot(p, vec2(-d.y, d.x)), pitch, lineWidth);
        if (hatch.w > 1.5) {
            l = max(l, hatch_line(dot(p, d), pitch, lineWidth));
        }
        float k = l * lineColor.a;
        col.rgb = mix(fillColor.rgb, lineColor.rgb, k);
        col.a = mix(fillColor.a, 1.0, k);
    }
    col.a *= opacity;
    if (useCount > 0.5) {
        // the n-th cap drawn on this pixel
        float n = max(floor(texelFetch(countTex, ivec2(gl_FragCoord.xy), 0).r * 255.0 / COUNT_UNITS + 0.5), 1.0);
        if (stripe.w > 0.5) {
            // stripes: of `total` overlapping caps, the n-th keeps every total-th stripe
            float total = floor(texelFetch(totalTex, ivec2(gl_FragCoord.xy), 0).r * 255.0 / COUNT_UNITS + 0.5);
            if (total > 1.5) {
                vec2 p = (stripe.x < 0.0) ? gl_FragCoord.xy : vUV;
                float idx = floor(dot(p, stripe.yz) / abs(stripe.x));
                if (abs(mod(idx, total) - (n - 1.0)) > 0.5) {
                    discard;
                }
            }
        }
        else {
            // running average: weight 1/n, so n overlapping caps blend equally
            col.a /= n;
        }
    }
    fragColor = col;
}
"""


_POWDER_FS = """
float hash(vec2 p) {
    return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453);
}

float speckle(vec2 uv, float cell) {
    // fades out where a cell gets smaller than about two pixels, so it never shimmers
    float px = max(fwidth(uv.x), fwidth(uv.y));
    float k = smoothstep(0.5, 2.0, cell / max(px, 1e-6));
    return (hash(floor(uv / cell)) - 0.5) * k;
}

void main() {
    float n = 0.7 * speckle(vUV, 0.4) + 0.3 * speckle(vUV + 17.0, 1.6);
    fragColor = vec4(fillColor.rgb * (1.0 + grain * 0.22 * n), 1.0);
}
"""


_SHELL_VS = """
void main() {
    vec3 p = pos + lift.xyz;
    vec4 c = viewProj * vec4(p, 1.0);
    gl_Position = viewProj * vec4(p + inward * side * max(band.x, band.y * c.w), 1.0);
    gl_Position.z -= band.z * gl_Position.w;
    vUV = uv;
}
"""
_SHELL_FS = """
void main() {
    fragColor = vec4(tint.rgb * texture(surface, vUV - floor(vUV)).rgb, 1.0);
}
"""


# Coverage count per pixel, accumulated additively in an 8-bit texture: each
# cap adds COUNT_UNITS/255, so up to 15 overlapping objects are counted exactly.
COUNT_UNITS = 16.0


def _make_shader(name, vs, fs, inputs, constants, samplers=(), varyings=()):
    info = gpu.types.GPUShaderCreateInfo()
    info.define("COUNT_STEP", f"{COUNT_UNITS / 255.0:.8f}")
    info.define("COUNT_UNITS", f"{COUNT_UNITS:.1f}")
    for i, (typ, nm) in enumerate(inputs):
        info.vertex_in(i, typ, nm)
    for typ, nm in constants:
        info.push_constant(typ, nm)
    for i, nm in enumerate(samplers):
        info.sampler(i, 'FLOAT_2D', nm)
    if varyings:
        iface = gpu.types.GPUStageInterfaceInfo(name + "_iface")
        for typ, nm in varyings:
            iface.smooth(typ, nm)
        info.vertex_out(iface)
    info.fragment_out(0, 'VEC4', "fragColor")
    info.vertex_source(vs)
    info.fragment_source(fs)
    return gpu.shader.create_from_info(info)


def _shader(kind):
    sh = _shaders.get(kind)
    if sh is not None:
        return sh
    if kind == "mask":
        sh = _make_shader("crosscut_mask", _MASK_VS, _MASK_FS,
                          [('VEC3', "pos")], [('MAT4', "viewProj")])
    elif kind == "wind":
        sh = _make_shader("crosscut_wind", _MASK_VS, _WIND_FS,
                          [('VEC3', "pos")], [('MAT4', "viewProj"), ('VEC4', "windColor")])
    elif kind == "resolve":
        sh = _make_shader("crosscut_resolve", _ACCUM_VS, _RESOLVE_FS,
                          [('VEC2', "pos")], [], samplers=["maskTex"])
    elif kind == "accum":
        sh = _make_shader("crosscut_accum", _ACCUM_VS, _ACCUM_FS,
                          [('VEC2', "pos")], [], samplers=["maskTex"])
    elif kind == "cap":
        sh = _make_shader(
            "crosscut_cap", _CAP_VS, _CAP_FS,
            [('VEC3', "pos"), ('VEC2', "uv")],
            [('MAT4', "viewProj"), ('VEC4', "fillColor"), ('VEC4', "lineColor"),
             ('VEC4', "hatch"), ('FLOAT', "threshold"), ('FLOAT', "lineWidth"), ('FLOAT', "useCount"),
             ('VEC4', "stripe"), ('FLOAT', "depthBias"), ('FLOAT', "opacity")],
            samplers=["maskTex", "countTex", "totalTex"], varyings=[('VEC2', "vUV")],
        )
    elif kind == "powder":
        sh = _make_shader("crosscut_powder", _CAP_VS, _POWDER_FS,
                          [('VEC3', "pos"), ('VEC2', "uv")],
                          [('MAT4', "viewProj"), ('VEC4', "fillColor"), ('FLOAT', "grain"), ('FLOAT', "depthBias")],
                          varyings=[('VEC2', "vUV")])
    elif kind == "shell":
        sh = _make_shader("crosscut_shell", _SHELL_VS, _SHELL_FS,
                          [('VEC3', "pos"), ('VEC3', "inward"), ('FLOAT', "side"), ('VEC2', "uv")],
                          [('MAT4', "viewProj"), ('VEC4', "lift"), ('VEC4', "band"), ('VEC4', "tint")],
                          samplers=["surface"], varyings=[('VEC2', "vUV")])
    elif kind == "line":
        sh = gpu.shader.from_builtin('POLYLINE_UNIFORM_COLOR')
    _shaders[kind] = sh
    return sh


def _offscreen(w, h):
    key = (w, h)
    pair = _offscreens.get(key)
    if pair is None:
        for old in _offscreens.values():
            for o in old:
                o.free()
        _offscreens.clear()
        # mask, running count, total count, winding
        pair = tuple(gpu.types.GPUOffScreen(w, h) for _ in range(4))
        _offscreens[key] = pair
    return pair


def _clear_bound():
    get = getattr(gpu.state, "active_framebuffer_get", None) or gpu.state.framebuffer_active_get
    get().clear(color=(0.0, 0.0, 0.0, 0.0))


def _vbatch(prim, attrs):
    """Batch from numpy arrays: attrs = {name: (array, comp_len)}."""
    fmt = gpu.types.GPUVertFormat()
    n = None
    for name, (arr, comp) in attrs.items():
        fmt.attr_add(id=name, comp_type='F32', len=comp, fetch_mode='FLOAT')
        n = len(arr)
    vbo = gpu.types.GPUVertBuf(fmt, n)
    for name, (arr, _comp) in attrs.items():
        vbo.attr_fill(name, np.ascontiguousarray(arr, dtype=np.float32))
    return gpu.types.GPUBatch(type=prim, buf=vbo)


_FULLSCREEN = None


def _fullscreen_batch():
    global _FULLSCREEN
    if _FULLSCREEN is None:
        quad = np.array([[-1, -1], [1, -1], [1, 1], [-1, -1], [1, 1], [-1, 1]], dtype=np.float32)
        _FULLSCREEN = _vbatch('TRIS', {"pos": (quad, 2)})
    return _FULLSCREEN


# --------------------------------------------------------------- clip sync

def _flat(planes):
    return np.array([list(p) for p in planes], dtype=np.float64).reshape(-1)


def _pad6(planes):
    out = [list(map(float, p)) for p in planes][:6]
    while len(out) < 6:
        out.append(list(sm.CLIP_NONE))
    return out


def _request_mode_off():
    def _off():
        try:
            s = bpy.context.scene.crosscut
            if s.mode != 'OFF':
                s.last_mode = s.mode
                s.mode = 'OFF'
        except (AttributeError, ReferenceError):
            pass
        return None
    bpy.app.timers.register(_off, first_interval=0.0)


def _iter_views():
    """(window, area, region, rv3d) for every 3D view region, quad views included."""
    wm = bpy.context.window_manager
    if wm is None:
        return
    for win in wm.windows:
        for area in win.screen.areas:
            if area.type != 'VIEW_3D':
                continue
            for region in area.regions:
                if region.type == 'WINDOW' and region.data is not None:
                    yield win, area, region, region.data


_to_prime = set()       # rv3d pointers that need a clipping box (see _prime_views)


def _prime(win, area, region, rv3d):
    """Give a view a clipping box so Blender applies its clip planes.

    Blender only clips a view that has a clipping bounding box (rv3d->clipbb),
    and only Alt+B (view3d.clip_border) creates one; RNA cannot. So the first
    time Crosscut takes over a view without existing clipping, it runs
    clip_border once with an empty rectangle (an empty box draws no
    clipping-region tint) and then writes its own planes back.
    """
    key = rv3d.as_pointer()
    _to_prime.discard(key)
    st = _clip_state.get(key)
    if st is None or st.get("ours") is None:
        return
    planes = st["ours"].reshape(6, 4).tolist()
    try:
        with bpy.context.temp_override(window=win, area=area, region=region):
            bpy.ops.view3d.clip_border(xmin=0, xmax=0, ymin=0, ymax=0, wait_for_input=False)
    except (RuntimeError, TypeError) as ex:
        print("Crosscut: could not enable clipping in a view:", ex)
        return
    rv3d.clip_planes = planes
    rv3d.use_clip_planes = True
    st["ours"] = _flat(rv3d.clip_planes)
    area.tag_redraw()


def _prime_views():
    pending = set(_to_prime)
    for win, area, region, rv3d in _iter_views():
        if rv3d.as_pointer() in pending:
            _prime(win, area, region, rv3d)
    _to_prime.clear()
    return None


def _request_prime(key):
    if not _to_prime:
        bpy.app.timers.register(_prime_views, first_interval=0.0)
    _to_prime.add(key)


def _remove_tints():
    """Swap a clipping region's tinted box for an empty one, keeping its planes (D-008)."""
    pending = set(_tint_pending)
    _tint_pending.clear()
    for win, area, region, rv3d in _iter_views():
        key = rv3d.as_pointer()
        if key not in pending or not rv3d.use_clip_planes or key in _clip_state:
            continue
        planes = [list(p) for p in rv3d.clip_planes]
        try:
            with bpy.context.temp_override(window=win, area=area, region=region):
                bpy.ops.view3d.clip_border(xmin=0, xmax=0, ymin=0, ymax=0, wait_for_input=False)
        except (RuntimeError, TypeError) as ex:
            print("Crosscut: could not remove the clipping tint:", ex)
            continue
        rv3d.clip_planes = planes
        rv3d.use_clip_planes = True
        _tint_gone.add(key)
        area.tag_redraw()
    return None


def _fit_tool_box(win, area, region, rv3d):
    """Fit this view's clipping box to what's kept. Painting, sculpting and some Edit Mode
    selection test against the box's four sides (rv3d->clipbb), not the planes, and the empty box
    of D-008 counts as everything clipped. Python can't write the box, but view3d.clip_border
    makes it from a rectangle in the view, so line the view up with the cut for a moment,
    with the rectangle's sides on the cut and any free sides far away (D-035)."""
    s = win.scene.crosscut
    planes = [list(p) for p in rv3d.clip_planes]
    keep = engine.compute_planes(s)
    pts = engine.target_points(bpy.context, s)
    size = float(np.linalg.norm(np.ptp(pts, axis=0))) if len(pts) else 100.0
    size = max(size, 1e-3)
    # each axis: (direction, low, high), None for a free side
    if keep:
        walls = keep[0]
        if len(walls) == 1 and sm.plane_is_degenerate(walls[0]) or walls[0][3] == sm.CLIP_ALL[3] and not any(walls[0][:3]):
            return  # a zero-thickness slice: nothing kept to work on
        x = sm.normalize(np.asarray(walls[0][:3], dtype=np.float64))
        low = -float(walls[0][3]) / float(np.linalg.norm(walls[0][:3]))
        high = low + s.thickness if len(walls) == 2 else None
        u, v = sm.plane_basis(x)
        axes = [(x, low, high), (u, None, None)]
    else:
        found = engine.clip_axes(rv3d)
        if len(found) != 2:
            return
        x = found[0][0]
        y = sm.normalize(found[1][0] - x * float(found[1][0] @ x))
        axes = [(x, found[0][1] - found[0][2], found[0][1] + found[0][2]),
                (y, found[1][1] - found[1][2], found[1][1] + found[1][2])]
    vx, vy = axes[0][0], axes[1][0]
    vz = np.cross(vx, vy)
    saved = (rv3d.view_location.copy(), rv3d.view_rotation.copy(), rv3d.view_distance, rv3d.view_perspective)
    far = 10000000  # px: a free side, well past the scene at this zoom
    try:
        from bpy_extras.view3d_utils import location_3d_to_region_2d
        rv3d.view_perspective = 'ORTHO'
        rv3d.view_rotation = Matrix((vx, vy, vz)).transposed().to_quaternion()
        rv3d.view_distance = size / 40.0
        centre = np.array([(lo + hi) / 2.0 if lo is not None and hi is not None else (lo if lo is not None else 0.0)
                           for _d, lo, hi in axes])
        origin = vx * centre[0] + vy * centre[1]
        rv3d.view_location = Vector(origin)
        rv3d.update()

        def pixel(a, b):
            p = location_3d_to_region_2d(region, rv3d, Vector(vx * a + vy * b))
            return p.x, p.y

        x0, y0 = pixel(centre[0], centre[1])
        x_lo = x0 - far if axes[0][1] is None else pixel(axes[0][1], centre[1])[0]
        x_hi = x0 + far if axes[0][2] is None else pixel(axes[0][2], centre[1])[0]
        y_lo = y0 - far if axes[1][1] is None else pixel(centre[0], axes[1][1])[1]
        y_hi = y0 + far if axes[1][2] is None else pixel(centre[0], axes[1][2])[1]
        with bpy.context.temp_override(window=win, area=area, region=region):
            bpy.ops.view3d.clip_border(xmin=int(round(x_lo)), xmax=int(round(x_hi)), ymin=int(round(y_lo)),
                                       ymax=int(round(y_hi)), wait_for_input=False)
    except (RuntimeError, TypeError, ValueError, AttributeError) as ex:
        print("Crosscut: could not fit the clipping box:", ex)
    finally:
        rv3d.view_location, rv3d.view_rotation, rv3d.view_distance, rv3d.view_perspective = saved
        rv3d.clip_planes = planes
        rv3d.use_clip_planes = True
        rv3d.update()
    area.tag_redraw()


def _fit_tool_boxes():
    pending = set(_tool_box_pending)
    _tool_box_pending.clear()
    for win, area, region, rv3d in _iter_views():
        key = rv3d.as_pointer()
        if key not in pending or not rv3d.use_clip_planes:
            continue
        _fit_tool_box(win, area, region, rv3d)
        _tool_box[key] = _flat(rv3d.clip_planes)
    return None


def request_tool_box(rv3d):
    """Fit the clipping box for tools outside Object Mode, once per set of planes."""
    key = rv3d.as_pointer()
    if key in _tool_box_pending:
        return
    last = _tool_box.get(key)
    if last is not None and np.allclose(last, _flat(rv3d.clip_planes), atol=1e-5, rtol=1e-6):
        return
    if not _tool_box_pending:
        bpy.app.timers.register(_fit_tool_boxes, first_interval=0.0)
    _tool_box_pending.add(key)


def has_saved_clip(rv3d):
    return rv3d.as_pointer() in _saved_clip


def restore_clip(context, rv3d):
    """Bring back the clipping region Section or Slice replaced, on an empty box (D-008).
    Run with the viewport region as context's region. False if there is none to bring back."""
    planes = _saved_clip.pop(rv3d.as_pointer(), None)
    if planes is None:
        return False
    bpy.ops.view3d.clip_border(xmin=0, xmax=0, ymin=0, ymax=0, wait_for_input=False)
    rv3d.clip_planes = planes
    rv3d.use_clip_planes = True
    _tint_gone.add(rv3d.as_pointer())
    return True


def forget_saved_clips():
    _saved_clip.clear()


def request_tint_removal(rv3d):
    """Remove Blender's tinted box from this view's clipping region, once, as soon
    as Blender lets an operator run."""
    key = rv3d.as_pointer()
    if key in _tint_gone or key in _tint_pending:
        return
    if not _tint_pending:
        bpy.app.timers.register(_remove_tints, first_interval=0.0)
    _tint_pending.add(key)


def sync_clip(rv3d, desired, area=None):
    """Make rv3d's clip planes match `desired` (list of planes), or release the
    view when desired is None: clipping off, whatever was there before (an
    Alt+B box's planes would come back without its shading, which only
    confuses). Returns True when Crosscut owns the clipping in this view."""
    key = rv3d.as_pointer()
    st = _clip_state.get(key)
    cur_on = bool(rv3d.use_clip_planes)
    cur = _flat(rv3d.clip_planes)

    if desired is None:
        if st is not None:
            ours = st.get("ours")
            if ours is not None and cur_on and np.allclose(cur, ours, atol=1e-5, rtol=1e-6):
                rv3d.clip_planes = [list(sm.CLIP_NONE)] * 6
                rv3d.use_clip_planes = False
                if area is not None:
                    area.tag_redraw()
            del _clip_state[key]
            _to_prime.discard(key)
        return False

    if st is not None and st.get("ours") is not None:
        if not cur_on or not np.allclose(cur, st["ours"], atol=1e-5, rtol=1e-6):
            # The user pressed Alt+B (toggles clipping off, or draws a new box):
            # hand control back and switch Crosscut off.
            del _clip_state[key]
            _to_prime.discard(key)
            _request_mode_off()
            return False
    else:
        if cur_on and any(not sm.plane_is_degenerate(p) for p in cur.reshape(6, 4)):
            _saved_clip[key] = cur.reshape(6, 4).tolist()  # so Clip can bring it back
        st = {"ours": None}
        _clip_state[key] = st
        # Without Alt+B there may be no clipping box at all; with Alt+B,
        # Blender would keep shading the area outside the old box. An empty
        # box fixes both.
        _request_prime(key)

    full = _pad6(desired)
    full_flat = _flat(full)
    if not (cur_on and np.allclose(cur, full_flat, atol=1e-6, rtol=1e-7)):
        rv3d.clip_planes = full
        rv3d.use_clip_planes = True
        if area is not None:
            area.tag_redraw()  # the scene was already drawn unclipped this frame
        full_flat = _flat(rv3d.clip_planes)  # what Blender actually stored (float32)
    st["ours"] = full_flat
    return True


def sync_views():
    """Apply the current settings to every 3D view right away, so the scene is
    drawn with the new planes in the same frame (called from property updates
    and operators; the draw callback only catches what these miss)."""
    for win, area, region, rv3d in _iter_views():
        scene = win.scene
        s = getattr(scene, "crosscut", None)
        if s is None:
            continue
        planes = engine.compute_planes(s)
        sync_clip(rv3d, planes[0] if planes else None, area)
        if rv3d.as_pointer() in _to_prime:
            _prime(win, area, region, rv3d)  # now, so the next frame is already clipped


def release_all_views():
    """Restore every view we touched (used on unregister)."""
    for _win, _area, _region, rv3d in _iter_views():
        sync_clip(rv3d, None)
    _clip_state.clear()
    _to_prime.clear()


# ------------------------------------------------------------------- colours

# The POST_VIEW overlay buffer is scene-linear and gets the view transform
# afterwards (checked in 4.2 and 5.2: a 0.85 fill showed as 237, not 217), so
# every colour sent to a shader must be linear. Colours picked in sRGB
# (COLOR_GAMMA properties, the palette, constants below) go through _lin().

def _srgb_to_linear(c):
    c = min(max(c, 0.0), 1.0)
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _lin(rgba):
    return tuple(_srgb_to_linear(c) for c in rgba[:3]) + tuple(rgba[3:])


def _linear_to_srgb(c):
    c = min(max(c, 0.0), 1.0)
    return c * 12.92 if c <= 0.0031308 else 1.055 * c ** (1.0 / 2.4) - 0.055


def _srgb(rgba):
    """Linear -> sRGB, for Blender's built-in line shader, which takes sRGB
    colours and converts them itself (unlike our own shaders, D-009)."""
    return tuple(_linear_to_srgb(c) for c in rgba[:3]) + tuple(rgba[3:])


def _is_plain(rgb):
    """Unsaturated (white / grey / black): Blender's defaults for objects and materials."""
    return max(rgb) - min(rgb) < 0.08


def _adjusted(s, rgb):
    """A color that came from a part (linear), adjusted by the Fill settings: unlit caps look
    brighter than the shaded surfaces around them."""
    r, g, b = rgb[:3]
    gray = 0.2126 * r + 0.7152 * g + 0.0722 * b
    k = s.fill_saturation
    c = np.array([gray + (r - gray) * k, gray + (g - gray) * k, gray + (b - gray) * k]) * s.fill_brightness
    a = s.fill_tint_amount
    if a > 0.0:
        c = c * (1.0 - a) + np.array(_lin(tuple(s.fill_tint))) * a
    return tuple(float(x) for x in c)


def target_color(s, target, shading):
    src = s.color_source
    owner = target.owner
    orig = target.orig
    auto = src == 'AUTO'
    if auto:
        ct = getattr(shading, "color_type", 'MATERIAL')
        src = {'OBJECT': 'OBJECT', 'MATERIAL': 'MATERIAL', 'RANDOM': 'RANDOM'}.get(ct, 'PALETTE')
    # Returns a linear colour (see _lin). Object and material colours are
    # already linear; the Cap Color and the palette are sRGB.
    if src == 'SINGLE':
        return _lin(s.single_color)
    if src == 'RANDOM':
        lib = orig.library.filepath if orig.library is not None else None
        return _adjusted(s, sm.random_shading_color(orig.name, lib))
    rgb = None
    if src == 'OBJECT':
        rgb = owner.color[:3]
    elif src == 'MATERIAL':
        mats = [sl.material for sl in getattr(orig, "material_slots", []) if sl.material]
        rgb = mats[0].diffuse_color[:3] if mats else owner.color[:3]
    if rgb is not None:
        if auto and _is_plain(rgb):
            # a white part with a white cap reads as uncut: use the Cap Color instead
            return _lin(s.single_color)
        return _adjusted(s, rgb)
    return _adjusted(s, _lin(sm.palette_color(owner.name_full)))


# --------------------------------------------------------------------- draw

def _view_dir_to_viewer(rv3d):
    vi = np.array(rv3d.view_matrix.inverted())
    return vi[:3, 2]


def _edge_on(rv3d, plane):
    """True when the view looks along the plane, so a cap on it has no area on
    screen. Alt+B's side planes pass through the eye until you orbit."""
    norm = float(np.linalg.norm(plane[:3]))
    if norm == 0:
        return True
    vi = np.array(rv3d.view_matrix.inverted())
    if rv3d.is_perspective:
        d = abs(float(np.dot(plane[:3], vi[:3, 3])) + float(plane[3])) / norm
        return d < max(rv3d.view_distance, 1e-6) * 1e-4
    return abs(float(np.dot(plane[:3], vi[:3, 2]))) / norm < 1e-4


def _cached(key, sig, build):
    hit = _batches.get(key)
    if hit is not None and hit[0] == sig:
        return hit[1]
    b = build()
    _batches[key] = (sig, b)
    return b


def _line_batch(target, ci, segs, serial, plane, bounds, toward, eps):
    sign = 1.0 if float(np.dot(plane[:3], toward)) >= 0 else -1.0
    q = round(math.log2(max(eps, 1e-12)))

    def build():
        # Blender clips the scene, not our overlay: trim the contour to the
        # other active planes (Alt+B's box) ourselves
        seg = sm.clip_segments(segs, bounds) if len(bounds) else segs
        if len(seg) == 0:
            return None
        n = sm.normalize(plane[:3]) * sign
        return _vbatch('LINES', {"pos": (seg.reshape(-1, 3) + n * (2.0 ** q), 3)})
    return _cached((target.key, ci, "line"), (serial, sign, q), build)


def _fan_batch(target, ci, segs, serial, n_open):
    def build():
        sg = sm.close_open_contours(segs) if n_open else segs
        return _vbatch('TRIS', {"pos": (sm.fan_triangles(sg), 3)})
    return _cached((target.key, ci, "fan"), serial, build)


def _quad_batch(poly, uv):
    tri = sm.fan_triangulate(poly)
    tuv = sm.fan_triangulate(np.concatenate([uv, np.zeros((len(uv), 1))], 1))[:, :2]
    return _vbatch('TRIS', {"pos": (tri, 3), "uv": (tuv, 2)})


def _cap_batch(key, sig, segs, plane, bounds):
    def build():
        poly, uv = sm.cap_polygon(segs, plane, bounds)
        return _quad_batch(poly, uv) if len(poly) >= 3 else None
    return _cached(key, sig, build)


HATCH_REFERENCE_SIZE = 50.0  # the part size the Spacing setting is for, in scene units


def _hatch_vec(s, index, style, angle_offset=0.0, size=None):
    if style == 'SOLID':
        return (1.0, 1.0, 0.0, 0.0)
    if s.hatch_space == 'SCREEN':
        base_pitch = s.hatch_pitch_px * bpy.context.preferences.system.ui_scale
    else:
        base_pitch = s.hatch_pitch
        if size:
            base_pitch *= (size / HATCH_REFERENCE_SIZE) ** s.hatch_scale
    ang, pitch = sm.hatch_for_index(index, math.degrees(s.hatch_angle) + angle_offset, base_pitch, s.hatch_vary)
    a = math.radians(ang)
    signed = -pitch if s.hatch_space == 'SCREEN' else pitch
    return (signed, math.cos(a), math.sin(a), 1.0 if style == 'HATCH' else 2.0)


# Pulls fills a few depth steps toward the viewer: a flat face lying on the plane
# would z-fight with a cap on it (in clip space, so it stays that few steps at any zoom).
CAP_DEPTH_BIAS = 1e-6


def _cap_uniforms(sh, vp, fill, line, hatch, threshold, width, mask_tex, count_tex=None,
                  total_tex=None, stripe=(1.0, 1.0, 0.0, 0.0), opacity=1.0, bias=CAP_DEPTH_BIAS):
    sh.bind()
    sh.uniform_float("viewProj", vp)
    sh.uniform_float("fillColor", fill)
    sh.uniform_float("lineColor", line)
    sh.uniform_float("hatch", hatch)
    sh.uniform_float("threshold", threshold)
    sh.uniform_float("lineWidth", width)
    sh.uniform_float("useCount", 1.0 if count_tex is not None else 0.0)
    sh.uniform_float("stripe", stripe if total_tex is not None else (1.0, 1.0, 0.0, 0.0))
    sh.uniform_float("depthBias", bias)
    sh.uniform_float("opacity", opacity)
    sh.uniform_sampler("maskTex", mask_tex)
    sh.uniform_sampler("countTex", count_tex if count_tex is not None else mask_tex)
    sh.uniform_sampler("totalTex", total_tex if total_tex is not None else mask_tex)


def _stripe_vec(s):
    """Stripes for overlapping caps, in the hatch space, 45 degrees off the hatch."""
    if s.hatch_space == 'SCREEN':
        pitch = -s.stripe_width_px * bpy.context.preferences.system.ui_scale
    else:
        pitch = s.stripe_width
    a = s.hatch_angle - math.radians(45.0)
    return (pitch, math.cos(a), math.sin(a), 1.0)


def _draw_mask(off, sh, vp, fan):
    """Even-odd coverage of one section into `off` (cleared first)."""
    with off.bind():
        _clear_bound()
        gpu.state.depth_test_set('NONE')
        gpu.state.face_culling_set('NONE')
        gpu.state.blend_set('INVERT')
        sh.bind()
        sh.uniform_float("viewProj", vp)
        fan.draw(sh)
        gpu.state.blend_set('NONE')


def _draw_winding_mask(off, wind_off, vp, fan):
    """Nonzero-winding coverage of one section into `off` (cleared first), for a
    mesh with consistent normals. Fan triangles add to red or green by which way
    they face; where the two differ the pixel is inside. Overlapping shells then
    stay filled, and shells with reversed normals still cut holes."""
    sh = _shader("wind")
    with wind_off.bind():
        _clear_bound()
        gpu.state.depth_test_set('NONE')
        gpu.state.blend_set('ADDITIVE')
        sh.bind()
        sh.uniform_float("viewProj", vp)
        gpu.state.face_culling_set('BACK')
        sh.uniform_float("windColor", (1.0 / 255.0, 0.0, 0.0, 1.0))
        fan.draw(sh)
        gpu.state.face_culling_set('FRONT')
        sh.uniform_float("windColor", (0.0, 1.0 / 255.0, 0.0, 1.0))
        fan.draw(sh)
        gpu.state.face_culling_set('NONE')
        gpu.state.blend_set('NONE')
    sh = _shader("resolve")
    with off.bind():
        _clear_bound()
        sh.bind()
        sh.uniform_sampler("maskTex", wind_off.texture_color)
        _fullscreen_batch().draw(sh)


def _add_coverage(off, sh, mask_off):
    """Add one COUNT_UNITS step to `off` wherever the mask is lit."""
    with off.bind():
        gpu.state.depth_test_set('NONE')
        gpu.state.blend_set('ADDITIVE')
        sh.bind()
        sh.uniform_sampler("maskTex", mask_off.texture_color)
        _fullscreen_batch().draw(sh)
        gpu.state.blend_set('NONE')


def auto_uses_cap_color(context, s):
    """Whether Auto colours currently give any target the Cap Color (a white
    or grey part under Object / Material shading), so the UI can hide it."""
    space = context.space_data
    shading = getattr(space, "shading", None)
    ct = getattr(shading, "color_type", 'MATERIAL')
    if ct not in {'OBJECT', 'MATERIAL'}:
        return False
    for ob in engine.original_targets(context, s)[:5000]:
        if ct == 'OBJECT':
            rgb = ob.color[:3]
        else:
            mats = [sl.material for sl in getattr(ob, "material_slots", []) if sl.material]
            rgb = mats[0].diffuse_color[:3] if mats else ob.color[:3]
        if _is_plain(rgb):
            return True
    return False


def backface_color():
    """The theme's Face Orientation back colour (red by default), linear."""
    try:
        c = bpy.context.preferences.themes[0].view_3d.face_back
    except (AttributeError, IndexError):
        c = (1.0, 0.0, 0.0)
    # a little darker, as the overlay shows it on a lit surface
    return _lin((c[0] * 0.75, c[1] * 0.75, c[2] * 0.75, 1.0))


CLIP_TINT_COLOR = (1.0, 1.0, 1.0, 0.012)
MEASURE_DEAD_PIXELS = 4
MEASURE_SNAP_REACH = 1.25  # of the anchor's 8-pixel radius: 10 pixels
MEASURE_TEXT_MIN, MEASURE_TEXT_MAX = 7.0, 200.0  # px
SELECT_WIDTH = 2.0  # px, about the width of Blender's selection outline
WARNING_RED = (1.0, 0.25, 0.2, 1.0)  # sRGB, for the readout


def _selection_colors(context):
    """(selected, active) outline colours from the theme, or None when the
    viewport doesn't show selection outlines."""
    overlay = getattr(context.space_data, "overlay", None)
    if overlay is None or not overlay.show_overlays or not overlay.show_outline_selected:
        return None
    if context.mode != 'OBJECT':
        return None  # Edit and paint modes show no object outline
    try:
        th = bpy.context.preferences.themes[0].view_3d
        sel, act = th.object_selected, th.object_active
    except (AttributeError, IndexError):
        sel, act = (0.93, 0.34, 0.0), (1.0, 0.67, 0.25)
    return tuple(sel[:3]) + (1.0,), tuple(act[:3]) + (1.0,)  # sRGB, as the line shader wants


def _selection_rank(target, selection):
    """0 unselected (or no outlines shown), 1 selected, 2 active."""
    if not selection:
        return 0
    ob = target.owner
    try:
        if not ob.select_get():
            return 0
    except RuntimeError:
        return 0
    return 2 if bpy.context.view_layer.objects.active == ob else 1


def _xray(shading):
    return shading.type == 'SOLID' and shading.show_xray


def _seen_from_behind(rv3d, plane):
    """True if the viewer is on a cap's kept side, looking at it from inside the part."""
    vi = np.array(rv3d.view_matrix.inverted())
    if rv3d.is_perspective:
        return float(plane[:3] @ vi[:3, 3]) + float(plane[3]) > 0.0
    return float(plane[:3] @ vi[:3, 2]) > 0.0


def _write_cap_depth(sh, vp, batch, threshold, tex):
    """Put a plane's finished caps into the depth buffer, so a slab's far contour
    can't show through the near cap. One pass after all of them: caps that wrote
    depth as they drew would z-fight with each other, being in the same plane."""
    gpu.state.color_mask_set(False, False, False, False)
    gpu.state.depth_test_set('LESS_EQUAL')
    gpu.state.depth_mask_set(True)
    gpu.state.blend_set('NONE')
    _cap_uniforms(sh, vp, (0.0, 0.0, 0.0, 1.0), (0.0, 0.0, 0.0, 1.0), (1.0, 1.0, 0.0, 0.0), threshold, 0.0,
                  tex, bias=0.0)
    batch.draw(sh)
    gpu.state.depth_mask_set(False)
    gpu.state.color_mask_set(True, True, True, True)


SHELL_MIN_PIXELS = 2.0
_white = []


def _white_texture():
    """1x1 white, sampled by a material with a flat color."""
    if not _white:
        data = gpu.types.Buffer('FLOAT', 4, [1.0, 1.0, 1.0, 1.0])
        _white.append(gpu.types.GPUTexture((1, 1), format='RGBA16F', data=data))
    return _white[0]


def _base_color_source(socket):
    """Follow a Base Color link to what's at the bottom of it: (image, UV map name or None), or
    (None, None). The first input of a Mix is the bottom layer of the 3MF importer's layers."""
    seen = 0
    while socket is not None and socket.is_linked and seen < 32:
        seen += 1
        node = socket.links[0].from_node
        if node.type == 'TEX_IMAGE':
            uv = None
            vector = node.inputs.get("Vector")
            if vector is not None and vector.is_linked and vector.links[0].from_node.type == 'UVMAP':
                uv = vector.links[0].from_node.uv_map
            return node.image, uv
        linked = [i for i in node.inputs if i.type == 'RGBA']
        socket = next((i for i in linked if i.is_linked), None)
    return None, None


def _surface_of(material):
    """(image or None, UV map name or None, flat scene-linear color) of a material's surface."""
    flat = (0.8, 0.8, 0.8)
    if material is None:
        return None, None, flat
    flat = tuple(material.diffuse_color[:3])
    for node in material.node_tree.nodes if material.node_tree is not None else ():
        if node.type == 'BSDF_PRINCIPLED':
            socket = node.inputs.get("Base Color")
            if socket is None:
                break
            if not socket.is_linked:
                return None, None, tuple(socket.default_value[:3])
            image, uv = _base_color_source(socket)
            return image, uv, flat
    return None, None, flat


def _shell_batches(t, ci, segs, serial, plane, depsgraph):
    """[(image or None, flat color, batch)]: a band along this part's contour for each material on it."""
    def build():
        info = engine.section_crossings(t, ci, serial)
        corners = engine.surface_corners(t, depsgraph)
        if info is None or corners is None or len(corners["material"]) == 0:
            return []
        slot = corners["material"][info["tri"]]
        slots = t.orig.material_slots
        flip = (np.linalg.det(t.matrix[:3, :3]) < 0.0) != engine.is_inside_out(t, depsgraph)
        centered = not engine.is_oriented(t, depsgraph)
        inward = sm.shell_inward(segs, sm.normalize(plane[:3]), flip)
        out = []
        for i in np.unique(slot):
            keep = slot == i
            image, uv_name, flat = _surface_of(slots[i].material if i < len(slots) else None)
            pos, into, side = sm.shell_quads(segs[keep], inward[keep], centered)
            layer = corners["uv"].get(uv_name) if uv_name else None
            if layer is None:
                layer = corners["uv"].get(corners["active"])
            if image is None or layer is None:
                image, uv = None, np.zeros((len(pos), 2), dtype=np.float32)
            else:
                part = {k: v[keep] for k, v in info.items()}
                uv = sm.repeat_for_shell(sm.crossing_values(part, layer))
            batch = _vbatch('TRIS', {"pos": (pos, 3), "inward": (into, 3),
                                     "side": (side.reshape(-1, 1), 1), "uv": (uv, 2)})
            out.append((image, flat, batch))
        return out
    return _cached((t.key, ci, "shell"), serial, build)


def _draw_shell(s, rv3d, vp, region, t, ci, segs, serial, plane, depsgraph, toward, eps, depth_test):
    """Print Preview, 580: the part's surface color along the inside of its contour. The GPU samples
    the textures, so scrubbing never reads their pixels in Python (D-042)."""
    batches = _shell_batches(t, ci, segs, serial, plane, depsgraph)
    if not batches:
        return
    sh = _shader("shell")
    gpu.state.depth_test_set(depth_test)
    gpu.state.depth_mask_set(False)
    gpu.state.blend_set('NONE')
    sh.bind()
    sign = 1.0 if float(np.dot(plane[:3], toward)) >= 0 else -1.0
    lift = sm.normalize(plane[:3]) * sign * eps
    # width of a pixel per unit of clip w: the same in perspective and orthographic
    per_pixel = 2.0 / (max(region.height, 1) * abs(rv3d.window_matrix[1][1]))
    ui = bpy.context.preferences.system.ui_scale
    sh.uniform_float("viewProj", vp)
    sh.uniform_float("lift", (lift[0], lift[1], lift[2], 0.0))
    # ahead of the cap, which is itself pulled forward by CAP_DEPTH_BIAS
    sh.uniform_float("band", (s.color_depth, SHELL_MIN_PIXELS * ui * per_pixel, CAP_DEPTH_BIAS * 2.0, 0.0))
    for image, flat, batch in batches:
        tex = None
        if image is not None:
            try:
                tex = gpu.texture.from_image(image)
            except (RuntimeError, SystemError, ValueError):
                tex = None
        sh.uniform_float("tint", (1.0, 1.0, 1.0, 1.0) if tex is not None else tuple(flat) + (1.0,))
        sh.uniform_sampler("surface", tex if tex is not None else _white_texture())
        batch.draw(sh)


def _draw_caps(context, s, rv3d, caps, show_fill, style, fill_override=None, outlines=True, shell=False):
    """Draw caps and outlines. fill_override: one fill colour for every target
    (no interference highlight), used for the Backfaces slice outline. Without
    outlines, only selected parts' contours are drawn. shell: Print Preview for
    the 580, the surface color along each contour."""
    region = context.region
    w, h = region.width, region.height
    if w < 2 or h < 2:
        return {}
    space = context.space_data
    shading = space.shading
    try:
        depsgraph = context.evaluated_depsgraph_get()
    except (RuntimeError, AttributeError):
        depsgraph = context.view_layer.depsgraph
    targets = engine.collect_targets(context, s, depsgraph)
    if not targets:
        return {"count": 0}

    vp = rv3d.perspective_matrix
    mask_off, accum_off, total_off, wind_off = _offscreen(w, h)
    mask_sh = _shader("mask")
    cap_sh = _shader("cap")
    accum_sh = _shader("accum")
    line_sh = _shader("line")
    toward = _view_dir_to_viewer(rv3d)
    eps = max(rv3d.view_distance, 1e-6) * 2e-4

    info = {"count": 0, "open": [], "open_mesh": [], "inside_out": [], "mixed_normals": []}
    overlay = getattr(space, "overlay", None)
    overlays_on = overlay is None or overlay.show_overlays
    face_orientation = overlays_on and overlay is not None and overlay.show_face_orientation
    live = set()
    colors = {}
    lines = []
    selection = _selection_colors(context)
    # X-ray: caps go translucent like the parts, and nothing hides anything
    xray = _xray(shading)
    xray_alpha = shading.xray_alpha if xray else 1.0
    depth_test = 'NONE' if xray else 'LESS_EQUAL'

    def part_mask(t, ci, segs, serial, n_open):
        fan = _fan_batch(t, ci, segs, serial, n_open)
        if oriented[t.key]:
            _draw_winding_mask(mask_off, wind_off, vp, fan)
        else:
            _draw_mask(mask_off, mask_sh, vp, fan)

    for ci, (plane, bounds) in enumerate(caps):
        hits = []
        oriented = {}
        for t in targets:
            live.add(t.key)
            res = engine.section(t, ci, plane, depsgraph, bounds, crossings=shell)
            if res is None:
                # a selected part with a face on the plane has no cut, but its
                # outline runs right there: don't let a neighbour's contour hide it
                if _selection_rank(t, selection):
                    res = engine.flush_section(t, ci, plane, depsgraph, bounds)
                    if res is not None:
                        lines.append((t, (ci, "flush"), res[0], res[2], plane, bounds, 0))
                continue
            segs, n_open, serial = res
            mesh_open = n_open > 0 or engine.is_open_mesh(t, depsgraph)
            hits.append((engine.hatch_index(context, t), t, segs, n_open, serial, mesh_open))
            oriented[t.key] = engine.is_oriented(t, depsgraph)
            if engine.is_inside_out(t, depsgraph):
                info["inside_out"].append(t.owner.name)
            elif not mesh_open and not oriented[t.key]:
                info["mixed_normals"].append(t.owner.name)
            if n_open:
                info["open"].append(t.owner.name)
            elif mesh_open:
                info["open_mesh"].append(t.owner.name)
        if not hits:
            continue
        info["count"] = max(info["count"], len(hits))

        # with Face Orientation on, a cap seen from inside the part reads as a backface
        # (a zero-thickness slice has no inside: neither side is its back)
        behind = (face_orientation and _seen_from_behind(rv3d, plane)
                  and not (s.mode == 'SLICE' and s.thickness <= 1e-9))
        if show_fill:
            # with overlapping parts, count coverage so overlaps can blend and
            # (optionally) get the interference hatching
            several = len(hits) > 1
            want_interference = s.overlap_style == 'HIGHLIGHT' and several and fill_override is None
            stripes = several and s.overlap_style == 'STRIPES' and fill_override is None
            if several:
                with accum_off.bind():
                    _clear_bound()
            if stripes:
                # stripes need the total overlap count up front
                with total_off.bind():
                    _clear_bound()
                for _idx, t, segs, n_open, serial, _mo in hits:
                    part_mask(t, ci, segs, serial, n_open)
                    _add_coverage(total_off, accum_sh, mask_off)
            for idx, t, segs, n_open, serial, mesh_open in hits:
                # 1) coverage mask
                part_mask(t, ci, segs, serial, n_open)
                # 2) count coverage
                if several:
                    _add_coverage(accum_off, accum_sh, mask_off)
                # 3) composite the cap into the viewport
                capb = _cap_batch((t.key, ci, "cap"), serial, segs, plane, bounds)
                if capb is not None:
                    if fill_override is not None:
                        col = fill_override
                    elif behind:
                        col = backface_color()
                    else:
                        col = colors.get(t.key)
                        if col is None:
                            col = target_color(s, t, shading)
                            colors[t.key] = col
                    fill = (col[0], col[1], col[2], 1.0)
                    linec = (col[0] * 0.02, col[1] * 0.02, col[2] * 0.02, 1.0)  # ~18% in sRGB
                    gpu.state.depth_test_set(depth_test)
                    gpu.state.depth_mask_set(False)
                    gpu.state.blend_set('ALPHA')
                    opacity = xray_alpha * s.fill_opacity
                    opacity *= s.open_opacity if mesh_open and fill_override is None else 1.0
                    hatch = _hatch_vec(s, idx, style, size=engine.part_size(t, depsgraph))
                    _cap_uniforms(cap_sh, vp, fill, linec, hatch, 0.5, s.hatch_width,
                                  mask_off.texture_color, accum_off.texture_color if several else None,
                                  total_off.texture_color if stripes else None, _stripe_vec(s), opacity)
                    capb.draw(cap_sh)
            # all of the plane's caps together, for the interference fill and the depth pass
            union = None
            if several:
                union = _cap_batch(("__interference__", ci, "cap"), tuple(hh[4] for hh in hits),
                                   np.concatenate([hh[2] for hh in hits]), plane, bounds)
            if want_interference:
                capb = union
                if capb is not None:
                    gpu.state.depth_test_set(depth_test)
                    gpu.state.depth_mask_set(False)
                    gpu.state.blend_set('ALPHA')
                    style_i = s.interference_style
                    hv = list(_hatch_vec(s, 0, 'SOLID' if style_i == 'SOLID' else 'HATCH'))
                    if style_i == 'CROSS':
                        hv[3] = 2.0
                    fill_i = _lin(tuple(s.interference_color) + (s.interference_opacity * xray_alpha,))
                    line_i = _lin(tuple(s.interference_line_color) + (1.0,))
                    _cap_uniforms(cap_sh, vp, fill_i, line_i, tuple(hv), 1.5 * COUNT_UNITS / 255.0, 0.18,
                                  accum_off.texture_color)
                    capb.draw(cap_sh)
            if not xray:
                if several and union is not None:
                    _write_cap_depth(cap_sh, vp, union, 0.5 * COUNT_UNITS / 255.0, accum_off.texture_color)
                elif not several:
                    capb = _cap_batch((hits[0][1].key, ci, "cap"), hits[0][4], hits[0][2], plane, bounds)
                    if capb is not None:
                        _write_cap_depth(cap_sh, vp, capb, 0.5, mask_off.texture_color)

        for _idx, t, segs, n_open, serial, _mo in hits:
            lines.append((t, ci, segs, serial, plane, bounds, n_open))
            if shell:
                _draw_shell(s, rv3d, vp, region, t, ci, segs, serial, plane, depsgraph, toward, eps, depth_test)

    # outlines last, on top of every cap. Selected parts get the selection
    # colour: it continues Blender's own outline along the cut, and in a
    # zero-thickness slice (everything clipped) it is the only sign of selection
    if lines and ((s.outline and outlines) or selection):
        gpu.state.depth_test_set(depth_test)
        gpu.state.depth_mask_set(False)
        gpu.state.blend_set('ALPHA')
        line_sh.bind()
        line_sh.uniform_float("viewportSize", (w, h))
        ui = bpy.context.preferences.system.ui_scale
        # selected last, so they win where contours meet
        lines.sort(key=lambda ln: _selection_rank(ln[0], selection))
        for t, ci, segs, serial, plane, bounds, _n_open in lines:
            rank = _selection_rank(t, selection)
            if not rank and not (s.outline and outlines):
                continue
            b = _line_batch(t, ci, segs, serial, plane, bounds, toward, eps)
            if b is None:
                continue
            width = s.outline_width
            col = fill_override or colors.get(t.key) or target_color(s, t, shading)
            if rank:
                c = selection[rank - 1]
                width = max(width, SELECT_WIDTH)
            elif show_fill:
                c = _srgb((col[0] * 0.01, col[1] * 0.01, col[2] * 0.01, 1.0))  # ~12% in sRGB
            else:
                c = _srgb((col[0], col[1], col[2], 1.0))
            line_sh.uniform_float("lineWidth", width * ui)
            line_sh.uniform_float("color", c)
            b.draw(line_sh)

    engine.prune(live)
    for k in [k for k in _batches if k[0] not in live and k[0] != "__interference__"]:
        del _batches[k]
    info["open"] = sorted(set(info["open"]))
    info["open_mesh"] = sorted(set(info["open_mesh"]) - set(info["open"]))
    info["inside_out"] = sorted(set(info["inside_out"]))
    info["mixed_normals"] = sorted(set(info["mixed_normals"]))
    return info


def _plane_colors(s, n):
    cols = [tuple(s.plane_color), tuple(s.plane_color_2)]
    return [cols[min(i, 1)] for i in range(n)]


def _frame_quads(context, s, caps):
    """One rectangle per cap plane, a little larger than the targets."""
    pts = engine.target_points(context, s)
    if len(pts) == 0:
        return []
    quads = []
    for plane, _bounds in caps:
        n = sm.normalize(plane[:3])
        u, v = sm.plane_basis(n)
        pu, pv = pts @ u, pts @ v
        pad = max(pu.max() - pu.min(), pv.max() - pv.min()) * 0.06
        u0, u1, v0, v1 = pu.min() - pad, pu.max() + pad, pv.min() - pad, pv.max() + pad
        origin = -n * (float(plane[3]) / float(np.linalg.norm(plane[:3])))
        uv = np.array([(u0, v0), (u1, v0), (u1, v1), (u0, v1)])
        quads.append((np.array([origin + u * a + v * b for a, b in uv]), uv))
    return quads


def _draw_plane_fill(context, s, rv3d, quads):
    """Tint (and optionally hatch) the plane so it reads at a glance. Drawn
    before the caps, which paint over it where the parts are cut."""
    region = context.region
    w, h = region.width, region.height
    if w < 2 or h < 2 or not quads:
        return
    sh = _shader("cap")
    mask_off = _offscreen(w, h)[0]
    vp = rv3d.perspective_matrix
    ui = bpy.context.preferences.system.ui_scale
    if s.plane_display == 'HATCH':
        a = math.radians(45.0)
        hatch = (-12.0 * ui, math.cos(a), math.sin(a), 1.0)
    else:
        hatch = (1.0, 1.0, 0.0, 0.0)
    colors = _plane_colors(s, len(quads))
    # Two slab planes: draw the nearer one, then the farther one only where the
    # nearer doesn't cover it, so looking through both doesn't double the tint
    vm = np.array(rv3d.view_matrix)
    depth = [float((vm @ np.append(poly.mean(0), 1.0))[2]) for poly, _uv in quads]
    order = sorted(range(len(quads)), key=lambda i: -depth[i])
    for k, i in enumerate(order):
        poly, uv = quads[i]
        batch = _quad_batch(poly, uv)
        if k > 0:
            near_poly = quads[order[0]][0]
            _draw_mask(mask_off, _shader("mask"), vp,
                       _vbatch('TRIS', {"pos": (sm.fan_triangulate(near_poly), 3)}))
        gpu.state.depth_test_set('NONE' if _xray(context.space_data.shading) else 'LESS_EQUAL')
        gpu.state.depth_mask_set(False)
        gpu.state.blend_set('ALPHA')
        c = colors[i]
        _cap_uniforms(sh, vp, _lin(c + (s.plane_opacity,)), _lin(c + (min(1.0, s.plane_opacity * 3.0),)),
                      hatch, 2.0 if k > 0 else -1.0, 0.08, mask_off.texture_color)
        batch.draw(sh)


def _draw_frame(context, s, quads):
    if not quads:
        return
    sh = _shader("line")
    region = context.region
    rv3d = context.region_data
    toward = _view_dir_to_viewer(rv3d)
    lift = max(rv3d.view_distance, 1e-6) * 4e-4
    # depth-tested like the contours, so the parts and a slab's near cap hide it
    gpu.state.depth_test_set('NONE' if _xray(context.space_data.shading) else 'LESS_EQUAL')
    gpu.state.depth_mask_set(False)
    gpu.state.blend_set('ALPHA')
    sh.bind()
    sh.uniform_float("viewportSize", (region.width, region.height))
    sh.uniform_float("lineWidth", 1.0)
    for (c, _uv), col in zip(quads, _plane_colors(s, len(quads)), strict=True):
        n = np.cross(c[1] - c[0], c[2] - c[0])
        n = sm.normalize(n) if np.linalg.norm(n) > 1e-12 else np.zeros(3)
        if float(np.dot(n, toward)) < 0:
            n = -n
        c = np.asarray(c) + n * lift
        segs = [tuple(c[(i + j) % 4]) for i in range(4) for j in (0, 1)]
        sh.uniform_float("color", col + (0.6,))  # sRGB: the built-in shader converts
        batch_for_shader(sh, 'LINES', {"pos": segs}).draw(sh)


# light for the powder bed's sides (world space, from above and front-left)
_POWDER_LIGHT = np.array([-0.3, -0.45, 0.84])


def _draw_powder(context, s, rv3d):
    """Print Preview: the powder bed, an opaque box filled up to the plane. It
    hides the parts below the plane (they are buried in powder); the caps drawn
    afterwards are the fused layer on its surface."""
    planes = engine.powder_planes(s)
    bed = engine.bed_bounds(context, s)
    if not planes or bed is None:
        return
    lo, hi = bed
    sh = _shader("powder")
    vp = rv3d.perspective_matrix
    base = np.array(_lin(tuple(s.powder_color) + (1.0,))[:3])
    light = _POWDER_LIGHT / np.linalg.norm(_POWDER_LIGHT)
    gpu.state.depth_test_set('LESS_EQUAL')
    gpu.state.blend_set('NONE')
    sh.bind()
    sh.uniform_float("viewProj", vp)
    sh.uniform_float("grain", s.powder_grain)
    sh.uniform_float("depthBias", 0.0)
    faces = sm.clipped_box_faces(lo, hi, planes)
    if s.mode == 'SLICE' and s.thickness <= 1e-9:
        faces = [f for f in faces if f[2] >= 0]  # a slice is one layer: the powder's surface alone
    for poly, n, cut in faces:
        # The surface on the plane writes no depth: the caps drawn next lie in the
        # same plane and must win there without z-fighting (they test against the
        # parts, which are all below it). The bed's sides do write depth.
        gpu.state.depth_mask_set(cut < 0)
        shade = 0.74 + 0.26 * max(float(np.dot(n, light)), 0.0)
        u, v = sm.plane_basis(n)
        tri = sm.fan_triangulate(poly)
        uv = np.stack([tri @ u, tri @ v], axis=1)
        sh.uniform_float("fillColor", tuple(base * shade) + (1.0,))
        _vbatch('TRIS', {"pos": (tri, 3), "uv": (uv, 2)}).draw(sh)


def _clip_prism(context, rv3d):
    """A clipping region's volume as triangles facing outward: its four walls, running
    from the viewer (or across the view, in orthographic) to well past the scene, plus ends."""
    walls = [np.array(p, dtype=np.float64) for p in rv3d.clip_planes
             if not sm.plane_is_degenerate(np.array(p, dtype=np.float64))]
    axes = engine.clip_axes(rv3d)
    if len(walls) != 4 or len(axes) != 2:
        return None
    w = sm.normalize(np.cross(axes[0][0], axes[1][0]))
    reach = context.space_data.clip_end * 0.45
    centre = float(np.array(rv3d.view_location) @ w)
    normals = np.array([p[:3] for p in walls])
    offsets = -np.array([p[3] for p in walls])
    # rcond: an orthographic box's walls are parallel but for rounding, so they meet nowhere
    apex, _res, rank, _sv = np.linalg.lstsq(normals, offsets, rcond=1e-3)
    if rank == 3:  # walls that meet at the eye the box was drawn from
        start = float(apex @ w)
        ahead = apex + w * max(reach, 1.0)
        toward = 1.0 if all(float(n @ ahead) >= o for n, o in zip(normals, offsets, strict=True)) else -1.0
        heights = (start + toward * reach * 1e-3, start + toward * reach)
    else:
        heights = (centre - reach, centre + reach)
    rings = []
    for h in heights:
        ring = []
        for i in range(4):
            j = (i + 1) % 4
            ring.append(np.linalg.solve(np.array([normals[i], normals[j], w]), np.array([offsets[i], offsets[j], h])))
        rings.append(ring)
    near, far = rings
    quads = [[near[i], far[i], far[(i + 1) % 4], near[(i + 1) % 4]] for i in range(4)] + [near, far]
    middle = np.mean(near + far, axis=0)
    tris = []
    for q in quads:
        centre_q = np.mean(q, axis=0)
        for a, b, c in ((q[0], q[1], q[2]), (q[0], q[2], q[3])):
            if float(np.cross(b - a, c - a) @ (centre_q - middle)) < 0.0:
                b, c = c, b
            tris += [tuple(a), tuple(b), tuple(c)]
    return tris


def _draw_clip_tint(context, rv3d):
    """The faint tint Blender gives a clipping region's volume, on the background only.
    Ours follows the region, and survives Section and Slice, as Blender's box can't."""
    tris = _clip_prism(context, rv3d)
    if tris is None:
        return
    sh = gpu.shader.from_builtin('UNIFORM_COLOR')
    gpu.state.depth_test_set('LESS_EQUAL')
    gpu.state.depth_mask_set(False)
    gpu.state.blend_set('ALPHA')
    gpu.state.face_culling_set('FRONT')  # the far side only, once per pixel, so parts hide it
    sh.bind()
    sh.uniform_float("color", CLIP_TINT_COLOR)
    batch_for_shader(sh, 'TRIS', {"pos": tris}).draw(sh)
    gpu.state.face_culling_set('NONE')


def _draw_annotations(context):
    """Draw 3D annotations again, over the caps. Blender draws finished annotations
    before add-on drawing (and only the stroke in progress after it), so a cap
    would otherwise cover them."""
    overlay = context.space_data.overlay
    data = getattr(context, "annotation_data", None)
    if data is None or not overlay.show_overlays or not overlay.show_annotation:
        return
    sh = _shader("line")
    region = context.region
    gpu.state.depth_test_set('NONE')
    gpu.state.depth_mask_set(False)
    gpu.state.blend_set('ALPHA')
    sh.bind()
    sh.uniform_float("viewportSize", (region.width, region.height))
    ui = bpy.context.preferences.system.ui_scale
    for layer in data.layers:
        frame = layer.active_frame
        if layer.annotation_hide or layer.is_ruler or frame is None:
            continue
        sh.uniform_float("lineWidth", max(float(layer.thickness), 1.0) * ui)
        sh.uniform_float("color", tuple(layer.color) + (layer.annotation_opacity,))
        for stroke in frame.strokes:
            if stroke.display_mode != '3DSPACE' or len(stroke.points) < 2:
                continue
            pts = np.empty(len(stroke.points) * 3, dtype=np.float32)
            stroke.points.foreach_get("co", pts)
            batch_for_shader(sh, 'LINE_STRIP', {"pos": pts.reshape(-1, 3)}).draw(sh)


def measure_running():
    return _measure["on"]


def measure_start():
    _measure.update(on=True, region=None, a=None, b=None, text="", la=None, lb=None, ltext="", cut=None, anchor=None)


def measure_stop():
    """Stop measuring. Pinned lines stay, until measure_clear."""
    _measure.update(on=False, region=None, a=None, b=None, text="", la=None, lb=None, ltext="", cut=None, anchor=None)


def measure_clear():
    _measure["dims"] = []


def measure_has_lines():
    return bool(_measure["dims"])


def native_or_lit(s, rv3d):
    return s.mode == 'OFF' and bool(rv3d.use_clip_planes)


def _caps_for(s, rv3d):
    planes = engine.compute_planes(s)
    if planes:
        return planes[1]
    if s.cap_style != 'BACKFACES' and rv3d.use_clip_planes:
        return [c for c in engine.native_caps(rv3d) if not _edge_on(rv3d, c[0])]
    return []


def _view_under_mouse(context, x, y):
    for area in context.window.screen.areas:
        if area.type != 'VIEW_3D':
            continue
        for region in area.regions:
            if (region.type == 'WINDOW' and region.data is not None
                    and region.x <= x < region.x + region.width and region.y <= y < region.y + region.height):
                # the sidebar and toolbar overlap the window region: not over them
                over_ui = any(r.type in {'UI', 'TOOLS', 'HEADER', 'TOOL_HEADER'} and r.width > 1 and r.height > 1
                              and r.x <= x < r.x + r.width and r.y <= y < r.y + r.height for r in area.regions)
                return None if over_ui else (area, region)
    return None


def _measure_at(context, region, x, y):
    """What's under the mouse, in the world: {"max": ..., "local": ...}, or None. Each is (end, end,
    length) or None: an overlap's width, or a single part's thickness."""
    from bpy_extras import view3d_utils
    scene = context.scene
    s = scene.crosscut
    rv3d = region.data
    xy = (x - region.x, y - region.y)
    origin = np.array(view3d_utils.region_2d_to_origin_3d(region, rv3d, xy))
    ray = np.array(view3d_utils.region_2d_to_vector_3d(region, rv3d, xy))
    hits = []
    for ci, (plane, bounds) in enumerate(_caps_for(s, rv3d)):
        plane = np.asarray(plane, dtype=np.float64)
        denom = float(plane[:3] @ ray)
        if abs(denom) < 1e-12:
            continue
        t = -(float(plane[:3] @ origin) + float(plane[3])) / denom
        p = origin + ray * t
        if rv3d.is_perspective and t < 0.0:
            continue
        inside = all(float(np.asarray(b)[:3] @ p) + float(np.asarray(b)[3]) >= -1e-6 for b in bounds)
        if inside:
            hits.append((t, ci, plane, bounds, p))
    depsgraph = context.evaluated_depsgraph_get()
    for _t, ci, plane, bounds, p in sorted(hits, key=lambda h: h[0]):
        parts = engine.targets_at(context, s, p, plane, depsgraph, ci, bounds)
        if not parts:
            continue
        n = sm.normalize(plane[:3])
        u, v = sm.plane_basis(n)
        basis = np.stack([u, v])
        # the search starts about 32 pixels across, whatever the zoom
        px = float(np.linalg.norm(np.array(view3d_utils.region_2d_to_location_3d(region, rv3d, (xy[0] + 16, xy[1]), p))
                                  - np.array(view3d_utils.region_2d_to_location_3d(region, rv3d, xy, p))))
        ta, sa = parts[0]
        if len(parts) >= 2 and not s.measure_ignore_overlaps:
            tb, sb = parts[1]
            res, near = sm.overlap_measures(sa @ basis.T, sb @ basis.T, p @ basis.T,
                                            (engine.is_oriented(ta, depsgraph), engine.is_oriented(tb, depsgraph)),
                                            half=max(px, 1e-6), local=s.measure_local)
            if not s.measure_max:
                res = None
        else:
            res, near = sm.section_measures(sa @ basis.T, p @ basis.T, engine.is_oriented(ta, depsgraph),
                                            half=max(px, 1e-6), local=s.measure_local,
                                            greatest=s.measure_section_max)
        lift = n * float(p @ n)
        world = [(m[1][0] * u + m[1][1] * v + lift, m[2][0] * u + m[2][1] * v + lift, m[0])
                 if m is not None else None for m in (res, near)]
        if not (world[0] or world[1]):
            return None
        overlap = len(parts) >= 2 and not s.measure_ignore_overlaps
        return {"max": world[0], "local": world[1],
                "cut": {"plane": plane, "basis": basis, "lift": lift,
                        "contours": [sa @ basis.T, parts[1][1] @ basis.T] if overlap else [sa @ basis.T],
                        "oriented": [engine.is_oriented(ta, depsgraph), engine.is_oriented(parts[1][0], depsgraph)]
                        if overlap else [engine.is_oriented(ta, depsgraph)]}}
    return None


def _on_cut(region, x, y, cut):
    """The mouse, on the plane of `cut`, in the plane's own 2D coordinates. None if it misses."""
    from bpy_extras import view3d_utils
    rv3d = region.data
    xy = (x - region.x, y - region.y)
    origin = np.array(view3d_utils.region_2d_to_origin_3d(region, rv3d, xy))
    ray = np.array(view3d_utils.region_2d_to_vector_3d(region, rv3d, xy))
    plane = cut["plane"]
    denom = float(plane[:3] @ ray)
    if abs(denom) < 1e-12:
        return None
    p = origin + ray * (-(float(plane[:3] @ origin) + float(plane[3])) / denom)
    return p @ cut["basis"].T


def _screen_distance(region, a, b, x, y):
    """Pixels from the mouse to the segment a-b on screen."""
    from bpy_extras.view3d_utils import location_3d_to_region_2d
    pa = location_3d_to_region_2d(region, region.data, tuple(a))
    pb = location_3d_to_region_2d(region, region.data, tuple(b))
    if pa is None or pb is None:
        return float("inf")
    m = np.array((x - region.x, y - region.y), dtype=np.float64)
    pa, pb = np.array(pa), np.array(pb)
    d = pb - pa
    t = min(1.0, max(0.0, float((m - pa) @ d) / max(float(d @ d), 1e-12)))
    return float(np.linalg.norm(pa + d * t - m))


def measure_click(context, x, y):
    """A click while measuring. On a showing line: anchor its nearer end, so the other end
    follows the mouse along a contour. While anchored: pin the line. True if it was used."""
    found = _view_under_mouse(context, x, y)
    if found is None:
        return False
    area, region = found
    pin = _measure["anchor"]
    if pin is not None:
        if pin["region"] != region.as_pointer():
            return False
        _measure["dims"].append((pin["a"], pin["b"], fmt_length(context.scene, float(np.linalg.norm(pin["a"] - pin["b"])))))
        _measure["anchor"] = None
        area.tag_redraw()
        return True
    if not _measure_shown() or _measure["region"] != region.as_pointer() or _measure["cut"] is None:
        return False
    lines = [(a, b) for a, b in ((_measure["a"], _measure["b"]), (_measure["la"], _measure["lb"])) if a is not None]
    a, b = min(lines, key=lambda ln: _screen_distance(region, ln[0], ln[1], x, y))
    # the end nearer the mouse stays; the other one follows it
    if _screen_distance(region, b, b, x, y) < _screen_distance(region, a, a, x, y):
        a, b = b, a
    cut = _measure["cut"]
    fixed, free = a @ cut["basis"].T, b @ cut["basis"].T
    # the free end keeps to the contour it's on (an overlap has two)
    which = min(range(len(cut["contours"])),
                key=lambda i: float(np.linalg.norm(sm.snap_to_contour(cut["contours"][i], free) - free)))
    # about 8 pixels: what counts as too close to the anchor to end on
    from bpy_extras import view3d_utils
    xy = (x - region.x, y - region.y)
    radius = float(np.linalg.norm(
        np.array(view3d_utils.region_2d_to_location_3d(region, region.data, (xy[0] + 8, xy[1]), tuple(a)))
        - np.array(view3d_utils.region_2d_to_location_3d(region, region.data, xy, tuple(a)))))
    _measure.update(region=None, a=None, b=None, text="", la=None, lb=None, ltext="")
    _measure["anchor"] = {"region": region.as_pointer(), "a": a, "b": b, "fixed": fixed, "click": (x, y), "moved": False,
                          "contour": cut["contours"][which], "oriented": cut["oriented"][which], "radius": radius,
                          "cut": cut, "normals": sm.anchor_normals(cut["contours"], fixed), "square": None}
    area.tag_redraw()
    return True


def _anchor_update(context, x, y, snap=True):
    pin = _measure["anchor"]
    found = _view_under_mouse(context, x, y)
    if found is None or found[1].as_pointer() != pin["region"]:
        return
    cut = pin["cut"]
    p = _on_cut(found[1], x, y, cut)
    if p is None:
        return
    # the line holds still until the mouse really leaves the click, as the click point is
    # near the anchor and tells nothing about where it's meant to go
    if not pin["moved"]:
        if max(abs(x - pin["click"][0]), abs(y - pin["click"][1])) < MEASURE_DEAD_PIXELS:
            return
        pin["moved"] = True
    hit = sm.snap_normal(pin["contour"], pin["fixed"], pin["normals"], p, pin["oriented"],
                         pin["radius"] * MEASURE_SNAP_REACH) if snap else None
    pin["square"] = None if hit is None else hit[1]
    q = sm.follow_cursor(pin["contour"], pin["fixed"], p, pin["oriented"], pin["radius"]) if hit is None else hit[0]
    pin["b"] = q[0] * cut["basis"][0] + q[1] * cut["basis"][1] + cut["lift"]
    found[0].tag_redraw()


def measure_cancel_anchor():
    """Esc while anchored: drop that line and keep measuring. True if there was one."""
    had = _measure["anchor"] is not None
    _measure["anchor"] = None
    return had


def measure_update(context, x, y, snap=True):
    """Called on every mouse move while measuring. `snap`: a line being placed may snap (D-041)."""
    if _measure["anchor"] is not None:
        _anchor_update(context, x, y, snap)
        return
    found = _view_under_mouse(context, x, y)
    res = None
    try:
        if found is not None:
            res = _measure_at(context, found[1], x, y)
    except Exception as ex:  # noqa: BLE001 - never let a hover spam errors
        msg = f"{type(ex).__name__}: {ex}"
        if msg not in _errors:
            _errors.add(msg)
            import traceback
            traceback.print_exc()
    had = _measure_shown()
    if res is None:
        _measure.update(region=None, a=None, b=None, text="", la=None, lb=None, ltext="", cut=None)
    else:
        _measure["cut"] = res["cut"]
        top, local = res["max"], res["local"]
        # the same line twice would only collide: show it once, as the max
        if top is not None and local is not None and abs(local[2] - top[2]) <= 0.01 * max(top[2], 1e-12) and (
                np.linalg.norm(local[0] - top[0]) + np.linalg.norm(local[1] - top[1]) < 2.0 * top[2]
                or np.linalg.norm(local[0] - top[1]) + np.linalg.norm(local[1] - top[0]) < 2.0 * top[2]):
            local = None
        _measure.update(region=found[1].as_pointer(),
                        a=None if top is None else top[0], b=None if top is None else top[1],
                        text="" if top is None else ("max " if local is not None else "") + fmt_length(context.scene, top[2]),
                        la=None if local is None else local[0], lb=None if local is None else local[1],
                        ltext="" if local is None else fmt_length(context.scene, local[2]))
    if found is not None and (had or res is not None):
        found[0].tag_redraw()


def _measure_shown():
    return _measure["a"] is not None or _measure["la"] is not None


def _measure_text_px(context, s, world):
    """The size to draw a length at: fixed in Screen space; in Model space, a height in
    scene units, like the hatching, but never too small to read."""
    ui = context.preferences.system.ui_scale
    if s.hatch_space == 'SCREEN':
        return s.measure_text_size * ui
    from bpy_extras.view3d_utils import location_3d_to_region_2d
    rv3d = context.region.data
    side = np.array(rv3d.view_matrix.inverted())[:3, 0]
    a = location_3d_to_region_2d(context.region, rv3d, tuple(world))
    b = location_3d_to_region_2d(context.region, rv3d, tuple(np.asarray(world) + side * s.measure_text_height))
    if a is None or b is None:
        return s.measure_text_size * ui
    return min(max(float((b - a).length), MEASURE_TEXT_MIN * ui), MEASURE_TEXT_MAX * ui)


def _measure_lines(context):
    """(end, end, text, color) of every measuring line to draw in this region."""
    s = context.scene.crosscut
    key = context.region.as_pointer()
    out = [(a, b, text, s.measure_color) for a, b, text in _measure["dims"]]
    pin = _measure["anchor"]
    if pin is not None and pin["region"] == key:
        out.append((pin["a"], pin["b"], fmt_length(context.scene, float(np.linalg.norm(pin["a"] - pin["b"]))),
                    s.measure_color))
    if _measure["region"] == key:
        if _measure["a"] is not None:
            out.append((_measure["a"], _measure["b"], _measure["text"], s.measure_max_color))
        if _measure["la"] is not None:
            out.append((_measure["la"], _measure["lb"], _measure["ltext"], s.measure_color))
    return out


def _draw_measure(context):
    lines = _measure_lines(context)
    if not lines or not context.space_data.overlay.show_overlays:
        return  # like the lengths, which the readout hides with overlays
    sh = _shader("line")
    region = context.region
    gpu.state.depth_test_set('NONE')
    gpu.state.depth_mask_set(False)
    gpu.state.blend_set('ALPHA')
    sh.bind()
    sh.uniform_float("viewportSize", (region.width, region.height))
    ui = bpy.context.preferences.system.ui_scale
    # dark under light, so it shows on any hatch
    for a, b, _text, color in lines:
        batch = batch_for_shader(sh, 'LINES', {"pos": [tuple(a), tuple(b)]})
        for width, c in ((5.0, (0.0, 0.0, 0.0, 0.9)), (2.5, tuple(color) + (1.0,))):
            sh.uniform_float("lineWidth", width * ui)
            sh.uniform_float("color", c)
            batch.draw(sh)
    pin = _measure["anchor"]
    if pin is not None and pin["square"] is not None and pin["region"] == region.as_pointer():
        # a square-corner mark at the anchor, in the plane of the cut
        m = pin["square"]
        basis = pin["cut"]["basis"]
        out = (m[0] * basis[0] + m[1] * basis[1]) * pin["radius"] * MEASURE_SNAP_REACH
        along = (-m[1] * basis[0] + m[0] * basis[1]) * pin["radius"] * MEASURE_SNAP_REACH
        corner = pin["a"] + out + along
        batch = batch_for_shader(sh, 'LINES', {"pos": [tuple(pin["a"] + along), tuple(corner),
                                                       tuple(corner), tuple(pin["a"] + out)]})
        for width, c in ((4.0, (0.0, 0.0, 0.0, 0.9)), (1.5, tuple(context.scene.crosscut.measure_color) + (1.0,))):
            sh.uniform_float("lineWidth", width * ui)
            sh.uniform_float("color", c)
            batch.draw(sh)


def draw_view():
    context = bpy.context
    rv3d = context.region_data
    scene = context.scene
    if rv3d is None or scene is None or not hasattr(scene, "crosscut"):
        return
    s = scene.crosscut
    key = context.region.as_pointer()
    try:
        planes = engine.compute_planes(s)
        ours = sync_clip(rv3d, planes[0] if planes else None, context.area)
        # Alt+B on the keyboard only redraws the viewport: refresh the sidebar's Clip button too
        lit = s.mode == 'OFF' and bool(rv3d.use_clip_planes)
        if _clip_lit.setdefault(rv3d.as_pointer(), lit) != lit:
            _clip_lit[rv3d.as_pointer()] = lit
            context.area.tag_redraw()
        if lit:
            _saved_clip.pop(rv3d.as_pointer(), None)  # a box is on: nothing to bring back
        tools = context.mode != 'OBJECT' and bool(rv3d.use_clip_planes) and (ours or lit)
        if tools:
            _tint_gone.discard(rv3d.as_pointer())
            request_tool_box(rv3d)
        elif rv3d.as_pointer() in _tool_box:
            del _tool_box[rv3d.as_pointer()]  # back to Object Mode: back to no box and no tint
            request_tint_removal(rv3d)
        elif lit:
            request_tint_removal(rv3d)  # it can't follow the region; _draw_clip_tint can
        elif not rv3d.use_clip_planes:
            _tint_gone.discard(rv3d.as_pointer())
        style = s.cap_style
        if ours:
            caps = planes[1]
        elif style != 'BACKFACES' and rv3d.use_clip_planes:
            # caps for the clipping region, minus its sides seen edge-on (nothing to see, all the cost)
            caps = [c for c in engine.native_caps(rv3d) if not _edge_on(rv3d, c[0])]
        else:
            caps = []
        shading_type = context.space_data.shading.type
        native = not ours and style != 'BACKFACES' and bool(rv3d.use_clip_planes)
        info = {"ours": ours, "native": native, "count": 0, "open": [], "open_mesh": [],
                "inside_out": [], "mixed_normals": []}
        # Blender only applies viewport clipping in Solid and Wireframe shading
        clips = shading_type in {'SOLID', 'WIREFRAME'}
        info["shading_note"] = bool(caps) and not clips
        if native_or_lit(s, rv3d) and s.clip_tint and context.space_data.overlay.show_overlays:
            _draw_clip_tint(context, rv3d)
        plane_shown = ours and s.plane_display != 'NONE' and context.space_data.overlay.show_overlays
        quads = _frame_quads(context, s, caps) if plane_shown and caps else []
        if quads and s.plane_display in {'TINT', 'HATCH'}:
            _draw_plane_fill(context, s, rv3d, quads)
        # caps are for Solid shading; Wireframe gets no caps or outlines
        solid = shading_type == 'SOLID'
        preview = s.print_preview and ours and solid
        if preview:
            _draw_powder(context, s, rv3d)
            fused = _lin(tuple(s.fused_color) + (1.0,))
            # one fused colour with no outlines: a part's inner shells shouldn't show
            info.update(_draw_caps(context, s, rv3d, caps, True, 'SOLID', fill_override=fused, outlines=False,
                                   shell=s.print_profile == 'MJF_580'))
        elif caps and solid and style != 'BACKFACES':
            info.update(_draw_caps(context, s, rv3d, caps, True, style))
        elif caps and solid and ours and s.mode == 'SLICE' and s.thickness <= 1e-9:
            # a zero-thickness slice clips everything, so with Backfaces there
            # would be nothing at all to see: show the cut as a backface-red fill
            info.update(_draw_caps(context, s, rv3d, caps, True, 'SOLID', fill_override=backface_color()))
        info["no_plane_object"] = s.mode != 'OFF' and s.orientation == 'OBJECT' and s.plane_object is None
        info["uncapped"] = engine.hidden_from_caps(context, s) if (ours or native) and solid else []
        if quads:
            _draw_frame(context, s, quads)
        if caps and solid:
            _draw_annotations(context)
        _draw_measure(context)
        _last_info[key] = info
    except Exception as ex:  # never let a drawing error spam every redraw
        msg = f"{type(ex).__name__}: {ex}"
        if msg not in _errors:
            _errors.add(msg)
            import traceback
            traceback.print_exc()
        _last_info[key] = {"error": msg}
    finally:
        gpu.state.blend_set('NONE')
        gpu.state.depth_test_set('NONE')
        gpu.state.depth_mask_set(False)


_UNIT_SCALE = {  # length_unit -> (metres per unit, suffix)
    'MICROMETERS': (1e-6, "µm"), 'MILLIMETERS': (1e-3, "mm"), 'CENTIMETERS': (1e-2, "cm"),
    'METERS': (1.0, "m"), 'KILOMETERS': (1e3, "km"),
    'THOU': (2.54e-5, "thou"), 'INCHES': (0.0254, "in"), 'FEET': (0.3048, "ft"), 'MILES': (1609.344, "mi"),
}


def fmt_length(scene, value):
    """A length in the scene's display unit (Scene > Units > Length), e.g. '12.000 mm'."""
    us = scene.unit_settings
    if us.system == 'NONE':
        return f"{value:.3f}"
    metres = value * us.scale_length
    unit = _UNIT_SCALE.get(us.length_unit)
    if unit is not None:
        return f"{metres / unit[0]:.3f} {unit[1]}"
    try:
        return bpy.utils.units.to_string(us.system, 'LENGTH', metres, precision=3)
    except (ValueError, TypeError):
        return f"{value:.3f}"


def _enum_name(s, prop):
    p = s.bl_rna.properties[prop]
    return p.enum_items[getattr(s, prop)].name


def _names(names):
    more = f" (+{len(names) - 3})" if len(names) > 3 else ""
    return ", ".join(names[:3]) + more


def readout_lines(scene, s, info):
    """(lines, warnings, severe warnings) shown at the bottom of the viewport."""
    lines, warn, severe = [], [], []
    if not info:
        return lines, warn, severe
    if "error" in info:
        warn.append("Crosscut draw error (see console): " + info["error"][:90])
    elif info.get("ours"):
        c = engine.plane_coordinate(s)
        if s.orientation == 'OBJECT':
            axis = f"{s.plane_object.name} {s.object_axis}" if s.plane_object else "?"
        else:
            axis = _enum_name(s, 'orientation')
        head = f"{_enum_name(s, 'mode')} {axis}  {fmt_length(scene, c)}"
        if s.mode == 'SLICE' and s.thickness > 0:
            head += f"  ±{fmt_length(scene, s.thickness / 2)}"
        if (s.print_preview or (s.range_source == 'OBJECT' and s.range_object is not None)) and s.step > 0:
            lo, hi = engine.scrub_range(s)
            k = int(round((c - lo) / s.step))
            total = int(round((hi - lo) / s.step))
            head += f"   {'layer' if s.print_preview else 'step'} {k} / {total}"
        head += "   Print Preview" if s.print_preview else f"   {_enum_name(s, 'cap_style')}"
        lines.append(head)
    elif info.get("native"):
        lines.append(f"Clipping Region   {_enum_name(s, 'cap_style')}")
    if info.get("no_plane_object"):
        warn.append("Object plane: pick an object (nothing is cut until then)")
    if info.get("uncapped"):
        warn.append("Not capped (Wire/Bounds display): " + _names(info["uncapped"]))
    if info.get("shading_note"):
        warn.append("Clipping works in Solid and Wireframe shading only; caps in Solid")
    if info.get("open_mesh"):
        warn.append("Open mesh, its cap may not be real material: " + _names(info["open_mesh"]))
    if info.get("mixed_normals"):
        warn.append("Flipped faces, overlaps may show as holes: " + _names(info["mixed_normals"]))
    if info.get("inside_out"):
        severe.append("Inside out: " + _names(info["inside_out"]))
    if info.get("open"):
        severe.append("Open section, gaps filled in by guesswork: " + _names(info["open"]))
    return lines, warn, severe


def draw_readout():
    context = bpy.context
    scene = context.scene
    if scene is None or not hasattr(scene, "crosscut"):
        return
    s = scene.crosscut
    overlay = getattr(context.space_data, "overlay", None)
    if overlay is not None and not overlay.show_overlays:
        return  # like Blender's own viewport text
    ui = context.preferences.system.ui_scale
    font = 0
    blf.size(font, 12 * ui)
    blf.enable(font, blf.SHADOW)
    blf.shadow(font, 3, 0.0, 0.0, 0.0, 0.85)
    measured = _measure_lines(context)
    if measured:
        from bpy_extras.view3d_utils import location_3d_to_region_2d
        blf.disable(font, blf.SHADOW)
        for a, b, text, color in measured:
            middle = 0.5 * (np.asarray(a) + np.asarray(b))
            p = location_3d_to_region_2d(context.region, context.region_data, tuple(middle))
            if p is None:
                continue
            blf.size(font, _measure_text_px(context, s, middle))
            x, y = p.x + 12 * ui, p.y + 8 * ui
            # a dark outline, to read on any hatch or highlight
            blf.color(font, 0.0, 0.0, 0.0, 1.0)
            for dx, dy in ((-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1)):
                blf.position(font, x + dx * 1.5 * ui, y + dy * 1.5 * ui, 0)
                blf.draw(font, text)
            blf.color(font, *color, 1.0)
            blf.position(font, x, y, 0)
            blf.draw(font, text)
        blf.enable(font, blf.SHADOW)
        blf.size(font, 12 * ui)
    if not s.show_readout:
        blf.disable(font, blf.SHADOW)
        return
    lines, warn, severe = readout_lines(scene, s, _last_info.get(context.region.as_pointer()))
    if _measure["on"]:
        lines = lines + ["Measure: click to place the line, Ctrl to stop it snapping, Esc to drop it" if _measure["anchor"] is not None
                         else "Measure: hover over a cut, click a line to adjust and pin it, Esc to stop"]
    elif _measure["dims"] and not s.measure_keep:
        lines = lines + ["Pinned measurements: Esc to clear"]
    if not lines and not warn and not severe:
        blf.disable(font, blf.SHADOW)
        return
    y = 16 * ui
    # centred: the bottom-left corner belongs to Blender's Adjust Last Operation panel
    for text, col in [(t, WARNING_RED) for t in reversed(severe)] + \
                     [(t, (1.0, 0.6, 0.1, 1.0)) for t in reversed(warn)] + \
                     [(t, (0.92, 0.92, 0.92, 1.0)) for t in reversed(lines)]:
        blf.color(font, *col)
        blf.position(font, (context.region.width - blf.dimensions(font, text)[0]) / 2, y, 0)
        blf.draw(font, text)
        y += 17 * ui
    blf.disable(font, blf.SHADOW)


def last_info(region):
    return _last_info.get(region.as_pointer()) if region else None


def register():
    _handles.append(bpy.types.SpaceView3D.draw_handler_add(draw_view, (), 'WINDOW', 'POST_VIEW'))
    _handles.append(bpy.types.SpaceView3D.draw_handler_add(draw_readout, (), 'WINDOW', 'POST_PIXEL'))


def unregister():
    try:
        release_all_views()
    except Exception:  # noqa: BLE001 - best effort during shutdown
        pass
    for h in _handles:
        try:
            bpy.types.SpaceView3D.draw_handler_remove(h, 'WINDOW')
        except ValueError:
            pass
    _handles.clear()
    for pair in _offscreens.values():
        for o in pair:
            o.free()
    _offscreens.clear()
    _batches.clear()
    _shaders.clear()
    _last_info.clear()
    _clip_lit.clear()
    _tint_gone.clear()
    _tint_pending.clear()
    _saved_clip.clear()
    _tool_box.clear()
    _tool_box_pending.clear()
    measure_stop()
    measure_clear()
    _errors.clear()
    global _FULLSCREEN
    _FULLSCREEN = None
