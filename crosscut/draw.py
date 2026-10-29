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
    fragColor = vec4(0.5, 0.0, 0.0, 1.0);
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
    if (m < threshold) {
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
        col = mix(fillColor, lineColor, l * lineColor.a);
        col.a = fillColor.a;
    }
    fragColor = col;
}
"""


def _make_shader(name, vs, fs, inputs, constants, samplers=(), varyings=()):
    info = gpu.types.GPUShaderCreateInfo()
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
             ('VEC4', "hatch"), ('FLOAT', "threshold"), ('FLOAT', "lineWidth")],
            samplers=["maskTex"], varyings=[('VEC2', "vUV")],
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
        pair = (gpu.types.GPUOffScreen(w, h), gpu.types.GPUOffScreen(w, h))
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
    """Make rv3d's clip planes match `desired` (list of planes) or hand them
    back to the user when desired is None. Returns True when Crosscut owns the
    clipping in this view."""
    key = rv3d.as_pointer()
    st = _clip_state.get(key)
    cur_on = bool(rv3d.use_clip_planes)
    cur = _flat(rv3d.clip_planes)

    if desired is None:
        if st is not None:
            ours = st.get("ours")
            if ours is not None and cur_on and np.allclose(cur, ours, atol=1e-5, rtol=1e-6):
                on, planes = st["saved"]
                rv3d.clip_planes = planes.reshape(6, 4).tolist()
                rv3d.use_clip_planes = on
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
        st = {"saved": (cur_on, cur.copy()), "ours": None}
        _clip_state[key] = st
        if not cur_on:
            # no Alt+B box in this view, so possibly no clipping box either
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


def _line_batch(target, ci, segs, serial, plane, toward, eps):
    sign = 1.0 if float(np.dot(plane[:3], toward)) >= 0 else -1.0
    n = sm.normalize(plane[:3]) * sign
    q = round(math.log2(max(eps, 1e-12)))
    sig = (serial, sign, q)
    k = (target.key, ci, "line")
    hit = _batches.get(k)
    if hit is not None and hit[0] == sig:
        return hit[1]
    pts = segs.reshape(-1, 3) + n * (2.0 ** q)
    b = _vbatch('LINES', {"pos": (pts, 3)})
    _batches[k] = (sig, b)
    return b


def _fan_batch(target, ci, segs, serial, n_open):
    k = (target.key, ci, "fan")
    sig = serial
    hit = _batches.get(k)
    if hit is not None and hit[0] == sig:
        return hit[1]
    if n_open:
        segs = sm.close_open_contours(segs)
    b = _vbatch('TRIS', {"pos": (sm.fan_triangles(segs), 3)})
    _batches[k] = (sig, b)
    return b


def _cap_batch(segs, plane, bounds):
    poly, uv = sm.cap_polygon(segs, plane, bounds)
    if len(poly) < 3:
        return None
    tri = sm.fan_triangulate(poly)
    tuv = sm.fan_triangulate(np.concatenate([uv, np.zeros((len(uv), 1))], 1))[:, :2]
    return _vbatch('TRIS', {"pos": (tri, 3), "uv": (tuv, 2)})


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


def _draw_caps(context, s, rv3d, caps, show_fill, style):
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
    mask_off, accum_off = _offscreen(w, h)
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
            res = engine.section(t, ci, plane, depsgraph)
            if res is None:
                continue
            segs, n_open, serial = res
            hits.append((idx, t, segs, n_open, serial))
        if not hits:
            continue
        info["count"] = max(info["count"], len(hits))

        if show_fill:
            want_interference = s.interference and len(hits) > 1
            if want_interference:
                with accum_off.bind():
                    _clear_bound()
            all_segs = []
            for idx, t, segs, n_open, serial in hits:
                # 1) even-odd mask
                with mask_off.bind():
                    _clear_bound()
                    gpu.state.depth_test_set('NONE')
                    gpu.state.face_culling_set('NONE')
                    gpu.state.blend_set('INVERT')
                    mask_sh.bind()
                    mask_sh.uniform_float("viewProj", vp)
                    _fan_batch(t, ci, segs, serial, n_open).draw(mask_sh)
                    gpu.state.blend_set('NONE')
                # 2) composite the cap into the viewport
                capb = _cap_batch(segs, plane, bounds)
                if capb is not None:
                    col = colors.get(t.key)
                    if col is None:
                        col = target_color(s, t, shading)
                        colors[t.key] = col
                    fill = (col[0], col[1], col[2], 1.0)
                    linec = (col[0] * 0.02, col[1] * 0.02, col[2] * 0.02, 1.0)  # ~18% in sRGB
                    gpu.state.depth_test_set('LESS_EQUAL')
                    gpu.state.depth_mask_set(False)
                    gpu.state.blend_set('ALPHA')
                    cap_sh.bind()
                    cap_sh.uniform_float("viewProj", vp)
                    cap_sh.uniform_float("fillColor", fill)
                    cap_sh.uniform_float("lineColor", linec)
                    cap_sh.uniform_float("hatch", _hatch_vec(s, idx, style))
                    cap_sh.uniform_float("threshold", 0.5)
                    cap_sh.uniform_float("lineWidth", s.hatch_width)
                    cap_sh.uniform_sampler("maskTex", mask_off.texture_color)
                    capb.draw(cap_sh)
                # 3) accumulate coverage for interference
                if want_interference:
                    with accum_off.bind():
                        gpu.state.depth_test_set('NONE')
                        gpu.state.blend_set('ADDITIVE')
                        accum_sh.bind()
                        accum_sh.uniform_sampler("maskTex", mask_off.texture_color)
                        _fullscreen_batch().draw(accum_sh)
                        gpu.state.blend_set('NONE')
                all_segs.append(segs)
            if want_interference:
                segs_all = np.concatenate(all_segs)
                capb = _cap_batch(segs_all, plane, bounds)
                if capb is not None:
                    gpu.state.depth_test_set('LESS_EQUAL')
                    gpu.state.depth_mask_set(False)
                    gpu.state.blend_set('ALPHA')
                    cap_sh.bind()
                    cap_sh.uniform_float("viewProj", vp)
                    cap_sh.uniform_float("fillColor", _lin((0.86, 0.10, 0.08, 1.0)))
                    cap_sh.uniform_float("lineColor", _lin((1.0, 0.85, 0.80, 1.0)))
                    hv = list(_hatch_vec(s, 0, 'HATCH'))
                    hv[3] = 2.0
                    cap_sh.uniform_float("hatch", tuple(hv))
                    cap_sh.uniform_float("threshold", 0.75)
                    cap_sh.uniform_float("lineWidth", 0.18)
                    cap_sh.uniform_sampler("maskTex", accum_off.texture_color)
                    capb.draw(cap_sh)

        for _idx, t, segs, n_open, serial in hits:
            if n_open:
                info["open"].append(t.owner.name)
            lines.append((t, ci, segs, serial, plane, n_open))

    # outlines last, on top of every cap
    if s.outline and lines:
        gpu.state.depth_test_set('LESS_EQUAL')
        gpu.state.depth_mask_set(False)
        gpu.state.blend_set('ALPHA')
        line_sh.bind()
        line_sh.uniform_float("viewportSize", (w, h))
        line_sh.uniform_float("lineWidth", s.outline_width * bpy.context.preferences.system.ui_scale)
        for t, ci, segs, serial, plane, n_open in lines:
            col = colors.get(t.key) or target_color(s, t, shading)
            if n_open:
                c = _lin((1.0, 0.55, 0.0, 1.0))  # orange: open / non-manifold contour
            elif show_fill:
                c = (col[0] * 0.01, col[1] * 0.01, col[2] * 0.01, 1.0)  # ~12% in sRGB
            else:
                c = (col[0], col[1], col[2], 1.0)
            line_sh.uniform_float("color", c)
            _line_batch(t, ci, segs, serial, plane, toward, eps).draw(line_sh)

    engine.prune(live)
    for k in [k for k in _batches if k[0] not in live]:
        del _batches[k]
    info["open"] = sorted(set(info["open"]))
    return info


def _draw_frame(context, s, rv3d, caps):
    pts = engine.target_points(context, s)
    if len(pts) == 0:
        return
    sh = _shader("line")
    region = context.region
    segs = []
    for plane, _bounds in caps:
        n = sm.normalize(plane[:3])
        u, v = sm.plane_basis(n)
        pu, pv = pts @ u, pts @ v
        pad = max(pu.max() - pu.min(), pv.max() - pv.min()) * 0.06
        u0, u1, v0, v1 = pu.min() - pad, pu.max() + pad, pv.min() - pad, pv.max() + pad
        origin = -n * (float(plane[3]) / float(np.linalg.norm(plane[:3])))
        c = [origin + u * a + v * b for a, b in ((u0, v0), (u1, v0), (u1, v1), (u0, v1))]
        for i in range(4):
            segs.extend([c[i], c[(i + 1) % 4]])
    if not segs:
        return
    gpu.state.depth_test_set('NONE')
    gpu.state.blend_set('ALPHA')
    sh.bind()
    sh.uniform_float("viewportSize", (region.width, region.height))
    sh.uniform_float("lineWidth", 1.0)
    sh.uniform_float("color", _lin((1.0, 0.75, 0.2, 0.45)))
    batch_for_shader(sh, 'LINES', {"pos": [tuple(p) for p in segs]}).draw(sh)


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
        if ours:
            caps = planes[1]
        elif s.cap_native and rv3d.use_clip_planes:
            caps = engine.native_caps(rv3d)
        else:
            caps = []
        shading_type = context.space_data.shading.type
        info = {"ours": ours, "native": (not ours and bool(caps)), "count": 0, "open": []}
        style = s.cap_style
        # Blender only applies viewport clipping in Solid and Wireframe shading
        info["shading_note"] = bool(caps) and shading_type in {'MATERIAL', 'RENDERED'}
        if caps and shading_type in {'SOLID', 'WIREFRAME'} and style != 'BACKFACES':
            # Wireframe shading: outlines only, no fill
            show_fill = shading_type != 'WIREFRAME'
            if show_fill or s.outline:
                info.update(_draw_caps(context, s, rv3d, caps, show_fill, style))
        if caps and ours and s.show_frame:
            _draw_frame(context, s, rv3d, caps)
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
            axis = s.orientation
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
    if info.get("shading_note"):
        warn.append("Clipping and caps only show in Solid / Wireframe shading")
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
