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

from . import engine
from . import section_math as sm

_handles = []
_shaders = {}
_offscreens = {}
_batches = {}          # (target key, cap index, kind) -> (signature, batch)
_clip_state = {}       # rv3d pointer -> {"ours": flat planes or None, "saved": (on, planes)}
_errors = set()
_last_info = {}        # per-region info for the readout


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
    elif kind == "accum":
        sh = _make_shader("crosscut_accum", _ACCUM_VS, _ACCUM_FS,
                          [('VEC2', "pos")], [], samplers=["maskTex"])
    elif kind == "cap":
        sh = _make_shader(
            "crosscut_cap", _CAP_VS, _CAP_FS,
            [('VEC3', "pos"), ('VEC2', "uv")],
            [('MAT4', "viewProj"), ('VEC4', "fillColor"), ('VEC4', "lineColor"),
             ('VEC4', "hatch"), ('FLOAT', "threshold"), ('FLOAT', "lineWidth"), ('FLOAT', "useCount"),
             ('VEC4', "stripe")],
            samplers=["maskTex", "countTex", "totalTex"], varyings=[('VEC2', "vUV")],
        )
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
        pair = tuple(gpu.types.GPUOffScreen(w, h) for _ in range(3))  # mask, running count, total count
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


def target_color(s, target, shading):
    src = s.color_source
    owner = target.owner
    orig = target.orig
    auto = src == 'AUTO'
    if auto:
        ct = getattr(shading, "color_type", 'MATERIAL')
        src = {'OBJECT': 'OBJECT', 'MATERIAL': 'MATERIAL'}.get(ct, 'PALETTE')
    # Returns a linear colour (see _lin). Object and material colours are
    # already linear; the Cap Color and the palette are sRGB.
    if src == 'SINGLE':
        return _lin(s.single_color)
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
        return tuple(rgb)
    return _lin(sm.palette_color(owner.name_full))


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


def _hatch_vec(s, index, style, angle_offset=0.0):
    if style == 'SOLID':
        return (1.0, 1.0, 0.0, 0.0)
    if s.hatch_space == 'SCREEN':
        base_pitch = s.hatch_pitch_px * bpy.context.preferences.system.ui_scale
    else:
        base_pitch = s.hatch_pitch
    ang, pitch = sm.hatch_for_index(index, math.degrees(s.hatch_angle) + angle_offset, base_pitch, s.hatch_vary)
    a = math.radians(ang)
    signed = -pitch if s.hatch_space == 'SCREEN' else pitch
    return (signed, math.cos(a), math.sin(a), 1.0 if style == 'HATCH' else 2.0)


def _cap_uniforms(sh, vp, fill, line, hatch, threshold, width, mask_tex, count_tex=None,
                  total_tex=None, stripe=(1.0, 1.0, 0.0, 0.0)):
    sh.bind()
    sh.uniform_float("viewProj", vp)
    sh.uniform_float("fillColor", fill)
    sh.uniform_float("lineColor", line)
    sh.uniform_float("hatch", hatch)
    sh.uniform_float("threshold", threshold)
    sh.uniform_float("lineWidth", width)
    sh.uniform_float("useCount", 1.0 if count_tex is not None else 0.0)
    sh.uniform_float("stripe", stripe if total_tex is not None else (1.0, 1.0, 0.0, 0.0))
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


SELECT_WIDTH = 2.0  # px, about the width of Blender's selection outline


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


def _draw_caps(context, s, rv3d, caps, show_fill, style, fill_override=None):
    """Draw caps and outlines. fill_override: one fill colour for every target
    (no interference highlight), used for the Backfaces slice outline."""
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
    mask_off, accum_off, total_off = _offscreen(w, h)
    mask_sh = _shader("mask")
    cap_sh = _shader("cap")
    accum_sh = _shader("accum")
    line_sh = _shader("line")
    toward = _view_dir_to_viewer(rv3d)
    eps = max(rv3d.view_distance, 1e-6) * 2e-4

    info = {"count": 0, "open": []}
    live = set()
    colors = {}
    lines = []

    for ci, (plane, bounds) in enumerate(caps):
        hits = []
        for idx, t in enumerate(targets):
            live.add(t.key)
            res = engine.section(t, ci, plane, depsgraph, bounds)
            if res is None:
                continue
            segs, n_open, serial = res
            hits.append((idx, t, segs, n_open, serial))
        if not hits:
            continue
        info["count"] = max(info["count"], len(hits))

        if show_fill:
            # with overlapping parts, count coverage so overlaps can blend and
            # (optionally) get the interference hatching
            several = len(hits) > 1
            want_interference = s.interference and several and fill_override is None
            stripes = several and s.overlap_style == 'STRIPES' and fill_override is None
            if several:
                with accum_off.bind():
                    _clear_bound()
            if stripes:
                # stripes need the total overlap count up front
                with total_off.bind():
                    _clear_bound()
                for _idx, t, segs, n_open, serial in hits:
                    _draw_mask(mask_off, mask_sh, vp, _fan_batch(t, ci, segs, serial, n_open))
                    _add_coverage(total_off, accum_sh, mask_off)
            for idx, t, segs, n_open, serial in hits:
                # 1) even-odd mask
                _draw_mask(mask_off, mask_sh, vp, _fan_batch(t, ci, segs, serial, n_open))
                # 2) count coverage
                if several:
                    _add_coverage(accum_off, accum_sh, mask_off)
                # 3) composite the cap into the viewport
                capb = _cap_batch((t.key, ci, "cap"), serial, segs, plane, bounds)
                if capb is not None:
                    if fill_override is not None:
                        col = fill_override
                    else:
                        col = colors.get(t.key)
                        if col is None:
                            col = target_color(s, t, shading)
                            colors[t.key] = col
                    fill = (col[0], col[1], col[2], 1.0)
                    linec = (col[0] * 0.02, col[1] * 0.02, col[2] * 0.02, 1.0)  # ~18% in sRGB
                    gpu.state.depth_test_set('LESS_EQUAL')
                    # write depth, so a slab's far contour can't show through the near cap
                    gpu.state.depth_mask_set(True)
                    gpu.state.blend_set('ALPHA')
                    _cap_uniforms(cap_sh, vp, fill, linec, _hatch_vec(s, idx, style), 0.5, s.hatch_width,
                                  mask_off.texture_color, accum_off.texture_color if several else None,
                                  total_off.texture_color if stripes else None, _stripe_vec(s))
                    capb.draw(cap_sh)
            if want_interference:
                serials = tuple(hh[4] for hh in hits)
                capb = _cap_batch(("__interference__", ci, "cap"), serials,
                                  np.concatenate([hh[2] for hh in hits]), plane, bounds)
                if capb is not None:
                    gpu.state.depth_test_set('LESS_EQUAL')
                    gpu.state.depth_mask_set(False)
                    gpu.state.blend_set('ALPHA')
                    style_i = s.interference_style
                    hv = list(_hatch_vec(s, 0, 'SOLID' if style_i == 'SOLID' else 'HATCH'))
                    if style_i == 'CROSS':
                        hv[3] = 2.0
                    fill_i = _lin(tuple(s.interference_color) + (s.interference_opacity,))
                    line_i = _lin(tuple(s.interference_line_color) + (1.0,))
                    _cap_uniforms(cap_sh, vp, fill_i, line_i, tuple(hv), 1.5 * COUNT_UNITS / 255.0, 0.18,
                                  accum_off.texture_color)
                    capb.draw(cap_sh)

        for _idx, t, segs, n_open, serial in hits:
            if n_open:
                info["open"].append(t.owner.name)
            lines.append((t, ci, segs, serial, plane, bounds, n_open))

    # outlines last, on top of every cap. Selected parts get the selection
    # colour: it continues Blender's own outline along the cut, and in a
    # zero-thickness slice (everything clipped) it is the only sign of selection
    selection = _selection_colors(context)
    if lines and (s.outline or selection):
        gpu.state.depth_test_set('LESS_EQUAL')
        gpu.state.depth_mask_set(False)
        gpu.state.blend_set('ALPHA')
        line_sh.bind()
        line_sh.uniform_float("viewportSize", (w, h))
        ui = bpy.context.preferences.system.ui_scale
        # selected last, so they win where contours meet
        lines.sort(key=lambda ln: _selection_rank(ln[0], selection))
        for t, ci, segs, serial, plane, bounds, n_open in lines:
            rank = _selection_rank(t, selection)
            if not rank and not s.outline:
                continue
            b = _line_batch(t, ci, segs, serial, plane, bounds, toward, eps)
            if b is None:
                continue
            width = s.outline_width
            col = fill_override or colors.get(t.key) or target_color(s, t, shading)
            if rank:
                c = selection[rank - 1]
                width = max(width, SELECT_WIDTH)
            elif n_open:
                c = (1.0, 0.55, 0.0, 1.0)  # orange: open / non-manifold contour
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
        gpu.state.depth_test_set('LESS_EQUAL')
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
    gpu.state.depth_test_set('LESS_EQUAL')
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
        style = s.cap_style
        if ours:
            caps = planes[1]
        elif style != 'BACKFACES' and rv3d.use_clip_planes:
            # caps for Alt+B, minus the box sides seen edge-on (nothing to see, all the cost)
            caps = [c for c in engine.native_caps(rv3d) if not _edge_on(rv3d, c[0])]
        else:
            caps = []
        shading_type = context.space_data.shading.type
        native = not ours and style != 'BACKFACES' and bool(rv3d.use_clip_planes)
        info = {"ours": ours, "native": native, "count": 0, "open": []}
        # Blender only applies viewport clipping in Solid and Wireframe shading
        clips = shading_type in {'SOLID', 'WIREFRAME'}
        info["shading_note"] = bool(caps) and not clips
        plane_shown = ours and s.plane_display != 'NONE'
        quads = _frame_quads(context, s, caps) if plane_shown and caps else []
        if quads and s.plane_display in {'TINT', 'HATCH'}:
            _draw_plane_fill(context, s, rv3d, quads)
        # caps are for Solid shading; Wireframe gets no caps or outlines
        solid = shading_type == 'SOLID'
        if caps and solid and style != 'BACKFACES':
            info.update(_draw_caps(context, s, rv3d, caps, True, style))
        elif caps and solid and ours and s.mode == 'SLICE' and s.thickness <= 1e-9:
            # a zero-thickness slice clips everything, so with Backfaces there
            # would be nothing at all to see: show the cut as a backface-red fill
            info.update(_draw_caps(context, s, rv3d, caps, True, 'SOLID', fill_override=backface_color()))
        info["no_plane_object"] = s.mode != 'OFF' and s.orientation == 'OBJECT' and s.plane_object is None
        info["uncapped"] = engine.hidden_from_caps(context, s) if (ours or native) and solid else []
        if quads:
            _draw_frame(context, s, quads)
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


def readout_lines(scene, s, info):
    """(lines, warnings) shown in the viewport's bottom-left corner."""
    lines, warn = [], []
    if not info:
        return lines, warn
    if "error" in info:
        warn.append("Crosscut draw error (see console): " + info["error"][:90])
    elif info.get("ours"):
        c = engine.plane_coordinate(s)
        if s.orientation == 'OBJECT':
            axis = s.plane_object.name if s.plane_object else "?"
        else:
            axis = _enum_name(s, 'orientation')
        head = f"{_enum_name(s, 'mode')} {axis}  {fmt_length(scene, c)}"
        if s.mode == 'SLICE' and s.thickness > 0:
            head += f"  ±{fmt_length(scene, s.thickness / 2)}"
        if s.range_source == 'OBJECT' and s.range_object is not None and s.step > 0:
            lo, hi = engine.scrub_range(s)
            k = int(round((c - lo) / s.step))
            total = int(round((hi - lo) / s.step))
            head += f"   step {k} / {total}"
        head += f"   {_enum_name(s, 'cap_style')}"
        lines.append(head)
    elif info.get("native"):
        lines.append(f"Alt+B clipping   {_enum_name(s, 'cap_style')}")
    if info.get("no_plane_object"):
        warn.append("Object plane: pick an object (nothing is cut until then)")
    if info.get("uncapped"):
        names = info["uncapped"]
        more = f" (+{len(names) - 3})" if len(names) > 3 else ""
        warn.append("Not capped (Wire/Bounds display): " + ", ".join(names[:3]) + more)
    if info.get("shading_note"):
        warn.append("Clipping works in Solid and Wireframe shading only; caps in Solid")
    if info.get("open"):
        names = info["open"]
        more = f" (+{len(names) - 3})" if len(names) > 3 else ""
        warn.append("Open section (non-manifold): " + ", ".join(names[:3]) + more)
    return lines, warn


def draw_readout():
    context = bpy.context
    scene = context.scene
    if scene is None or not hasattr(scene, "crosscut"):
        return
    s = scene.crosscut
    if not s.show_readout:
        return
    lines, warn = readout_lines(scene, s, _last_info.get(context.region.as_pointer()))
    if not lines and not warn:
        return
    ui = context.preferences.system.ui_scale
    font = 0
    blf.size(font, 12 * ui)
    blf.enable(font, blf.SHADOW)
    blf.shadow(font, 3, 0.0, 0.0, 0.0, 0.85)
    x = 16 * ui
    y = 16 * ui
    for text, col in [(t, (1.0, 0.6, 0.1, 1.0)) for t in reversed(warn)] + \
                     [(t, (0.92, 0.92, 0.92, 1.0)) for t in reversed(lines)]:
        blf.color(font, *col)
        blf.position(font, x, y, 0)
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
    _errors.clear()
    global _FULLSCREEN
    _FULLSCREEN = None
