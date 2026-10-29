# SPDX-License-Identifier: GPL-3.0-or-later
"""Pure-numpy geometry for Crosscut. No bpy imports, so it can be unit tested
outside Blender.

Conventions
-----------
A plane is a 4-vector ``(nx, ny, nz, d)``. A point ``p`` is *kept* (not clipped)
when ``dot(n, p) + d >= 0``; this matches Blender's ``RegionView3D.clip_planes``.
"""

import numpy as np

# A plane that clips everything (n = 0, d = -1). Used for "section only" slices.
CLIP_ALL = (0.0, 0.0, 0.0, -1.0)
# A plane that clips nothing. Fills unused slots of Blender's 6 clip planes.
CLIP_NONE = (0.0, 0.0, 0.0, 1.0)


def normalize(v):
    v = np.asarray(v, dtype=np.float64)
    n = np.linalg.norm(v)
    return v / n if n > 0 else v


def plane_from_point_normal(point, normal):
    """Plane keeping the half-space the normal points into."""
    n = normalize(normal)
    return np.array([n[0], n[1], n[2], -float(np.dot(n, point))])


def flip_plane(plane):
    return -np.asarray(plane, dtype=np.float64)


def plane_is_degenerate(plane, eps=1e-12):
    return float(np.dot(plane[:3], plane[:3])) < eps


def plane_basis(normal):
    """Orthonormal (u, v) spanning the plane, stable for axis-aligned normals.

    For a Z plane, u = +X and v = +Y, so hatch angles read naturally from the
    top view.
    """
    n = normalize(normal)
    # pick the world axis least aligned with n as the reference for u
    ref = np.array([0.0, 0.0, 1.0]) if abs(n[2]) < 0.9 else np.array([0.0, 1.0, 0.0])
    if abs(n[2]) >= 0.9:
        # Z-ish plane: u along +X projected
        u = np.array([1.0, 0.0, 0.0]) - n * n[0]
    else:
        u = np.cross(ref, n)
    u = normalize(u)
    v = np.cross(n, u)
    return u, v


def plane_to_local(plane, matrix_world):
    """Express a world-space plane in an object's local space.

    p_w = A p_l + t  =>  n.p_w + d = (A^T n).p_l + (n.t + d)
    The result is not normalized; only signs and ratios are used downstream.
    """
    m = np.asarray(matrix_world, dtype=np.float64)
    a = m[:3, :3]
    t = m[:3, 3]
    n = np.asarray(plane[:3], dtype=np.float64)
    return np.concatenate([a.T @ n, [float(n @ t) + float(plane[3])]])


def transform_points(points, matrix_world):
    m = np.asarray(matrix_world, dtype=np.float64)
    return points @ m[:3, :3].T + m[:3, 3]


def bbox_crosses_plane(bb_min, bb_max, plane):
    """True when an axis-aligned box straddles (or touches) the plane."""
    n = np.asarray(plane[:3])
    lo = np.where(n >= 0, bb_min, bb_max)
    hi = np.where(n >= 0, bb_max, bb_min)
    return (n @ lo + plane[3]) <= 0.0 <= (n @ hi + plane[3])


def _lex_less(a, b):
    """Row-wise lexicographic a < b for (..., 3) arrays."""
    return (a[..., 0] < b[..., 0]) | (
        (a[..., 0] == b[..., 0])
        & ((a[..., 1] < b[..., 1]) | ((a[..., 1] == b[..., 1]) & (a[..., 2] < b[..., 2])))
    )


def section_segments(verts, tris, plane, cols=None):
    """Intersect a triangle mesh with a plane.

    verts: (N, 3) float, tris: (M, 3) int, plane: 4-vector in the same space.
    Returns (K, 2, 3) float64 segment endpoints.

    Watertightness: every crossing edge is evaluated with its endpoints in a
    canonical (lexicographic by coordinate) order, so two triangles sharing an
    edge produce bit-identical points, even when the mesh is a triangle soup
    with duplicated vertices. Vertices exactly on the plane count as "kept"
    (>= 0), which gives a consistent half-open classification: each triangle has
    exactly 0 or 2 crossing edges.

    cols: optional (tris[:, 0], tris[:, 1], tris[:, 2]) as contiguous arrays,
    cached by the caller; makes the crossing test about 4x faster.
    """
    verts = np.asarray(verts, dtype=np.float64)
    tris = np.asarray(tris, dtype=np.int64)
    if len(tris) == 0:
        return np.zeros((0, 2, 3))
    s = verts @ np.asarray(plane[:3], dtype=np.float64) + float(plane[3])
    pos = s >= 0.0
    if cols is None:
        cols = (tris[:, 0], tris[:, 1], tris[:, 2])
    p0, p1, p2 = pos[cols[0]], pos[cols[1]], pos[cols[2]]
    keep = (p0 != p1) | (p1 != p2)
    if not keep.any():
        return np.zeros((0, 2, 3))
    tm = tris[keep]
    tpm = np.stack([p0[keep], p1[keep], p2[keep]], axis=1)
    ia = tm
    ib = tm[:, [1, 2, 0]]
    cross = tpm != tpm[:, [1, 2, 0]]  # exactly two True per row
    ea = ia[cross]
    eb = ib[cross]
    a = verts[ea]
    b = verts[eb]
    sa = s[ea]
    sb = s[eb]
    swap = _lex_less(b, a)
    a2 = np.where(swap[:, None], b, a)
    b2 = np.where(swap[:, None], a, b)
    sa2 = np.where(swap, sb, sa)
    sb2 = np.where(swap, sa, sb)
    t = sa2 / (sa2 - sb2)
    p = a2 + t[:, None] * (b2 - a2)
    # snap exact vertex hits so neighbouring edges agree bit-for-bit
    p = np.where((t == 0.0)[:, None], a2, p)
    p = np.where((t == 1.0)[:, None], b2, p)
    return p.reshape(-1, 2, 3)


def open_endpoint_count(segments):
    """Number of segment endpoints that are not shared by an even number of
    segments. Zero means every contour is closed (watertight cross-section)."""
    if len(segments) == 0:
        return 0
    pts = np.ascontiguousarray(segments.reshape(-1, 3))
    keys = pts.view(np.dtype((np.void, pts.dtype.itemsize * 3))).ravel()
    _, counts = np.unique(keys, return_counts=True)
    return int(np.count_nonzero(counts % 2))


def close_open_contours(segments, max_open=4096):
    """Add segments that join open endpoints pairwise (nearest first), so an
    almost-closed section from a slightly non-manifold mesh still fills
    sensibly instead of producing even-odd garbage. Returns segments unchanged
    when every contour is closed or there are too many open ends to pair."""
    if len(segments) == 0:
        return segments
    pts = np.ascontiguousarray(segments.reshape(-1, 3))
    keys = pts.view(np.dtype((np.void, pts.dtype.itemsize * 3))).ravel()
    _, first, counts = np.unique(keys, return_index=True, return_counts=True)
    ends = pts[first[counts % 2 == 1]]
    if len(ends) < 2 or len(ends) > max_open:
        return segments
    d = np.linalg.norm(ends[:, None, :] - ends[None, :, :], axis=2)
    np.fill_diagonal(d, np.inf)
    extra = []
    free = np.ones(len(ends), dtype=bool)
    for flat in np.argsort(d, axis=None):
        i, j = divmod(int(flat), len(ends))
        if i < j and free[i] and free[j]:
            extra.append((ends[i], ends[j]))
            free[i] = free[j] = False
            if not free.any():
                break
    if not extra:
        return segments
    return np.concatenate([segments, np.array(extra, dtype=segments.dtype)])


def fan_triangles(segments, apex=None):
    """Triangles (apex, a, b) for each segment, as a flat (K*3, 3) float32 array.

    Rasterized with XOR / invert blending, a pixel ends up "on" exactly when it
    is covered an odd number of times, i.e. when it lies inside the closed
    cross-section (even-odd rule). No contour chaining or triangulation is
    needed, and holes come out right automatically.
    """
    if len(segments) == 0:
        return np.zeros((0, 3), dtype=np.float32)
    if apex is None:
        apex = segments.reshape(-1, 3).mean(axis=0)
    k = len(segments)
    out = np.empty((k, 3, 3), dtype=np.float64)
    out[:, 0] = apex
    out[:, 1] = segments[:, 0]
    out[:, 2] = segments[:, 1]
    return out.reshape(-1, 3).astype(np.float32)


def clip_convex_polygon(poly, planes):
    """Sutherland-Hodgman: keep the part of a convex polygon (P, 3) on the kept
    side of every plane."""
    pts = [np.asarray(p, dtype=np.float64) for p in poly]
    for pl in planes:
        if plane_is_degenerate(pl):
            if pl[3] < 0:
                return np.zeros((0, 3))
            continue
        n = np.asarray(pl[:3])
        d = float(pl[3])
        out = []
        m = len(pts)
        for i in range(m):
            cur = pts[i]
            nxt = pts[(i + 1) % m]
            dc = n @ cur + d
            dn = n @ nxt + d
            if dc >= 0:
                out.append(cur)
            if (dc >= 0) != (dn >= 0):
                t = dc / (dc - dn)
                out.append(cur + t * (nxt - cur))
        pts = out
        if len(pts) < 3:
            return np.zeros((0, 3))
    return np.array(pts)


def clip_segments(segments, planes):
    """Keep the parts of segments (K, 2, 3) on the kept side of every plane."""
    seg = np.asarray(segments, dtype=np.float64)
    for pl in planes:
        if len(seg) == 0:
            break
        if plane_is_degenerate(pl):
            if pl[3] < 0:
                return np.zeros((0, 2, 3))
            continue
        n = np.asarray(pl[:3], dtype=np.float64)
        da = seg[:, 0] @ n + float(pl[3])
        db = seg[:, 1] @ n + float(pl[3])
        keep = (da >= 0) | (db >= 0)
        seg, da, db = seg[keep], da[keep], db[keep]
        part = (da < 0) | (db < 0)
        if part.any():
            a, b = seg[part, 0], seg[part, 1]
            t = (da[part] / (da[part] - db[part]))[:, None]
            p = a + t * (b - a)
            a = np.where((da[part] < 0)[:, None], p, a)
            b = np.where((db[part] < 0)[:, None], p, b)
            seg = seg.copy()
            seg[part, 0] = a
            seg[part, 1] = b
    return seg


def box_section_polygon(plane, lo, hi):
    """Convex polygon where a plane cuts the axis-aligned box [lo, hi] (may be empty)."""
    lo = np.asarray(lo, dtype=np.float64)
    hi = np.asarray(hi, dtype=np.float64)
    n = normalize(plane[:3])
    norm = float(np.linalg.norm(plane[:3]))
    if norm == 0:
        return np.zeros((0, 3))
    c = 0.5 * (lo + hi)
    c = c - n * ((float(np.dot(plane[:3], c)) + float(plane[3])) / norm)
    r = float(np.linalg.norm(hi - lo)) + 1e-9
    u, v = plane_basis(n)
    sq = np.array([c - u * r - v * r, c + u * r - v * r, c + u * r + v * r, c - u * r + v * r])
    faces = [np.array([1.0, 0, 0, -lo[0]]), np.array([-1.0, 0, 0, hi[0]]),
             np.array([0, 1.0, 0, -lo[1]]), np.array([0, -1.0, 0, hi[1]]),
             np.array([0, 0, 1.0, -lo[2]]), np.array([0, 0, -1.0, hi[2]])]
    return clip_convex_polygon(sq, faces)


def cap_polygon(segments, plane, bound_planes=(), margin=0.02):
    """Convex polygon on the plane that covers all segments, clipped by the
    other active clip planes. Returns (poly (P,3), uv (P,2)); uv are plane-local
    coordinates (scene units) used for model-space hatching."""
    n = normalize(plane[:3])
    u, v = plane_basis(n)
    pts = segments.reshape(-1, 3)
    pu = pts @ u
    pv = pts @ v
    pad = max(pu.max() - pu.min(), pv.max() - pv.min(), 1e-6) * margin
    u0, u1 = pu.min() - pad, pu.max() + pad
    v0, v1 = pv.min() - pad, pv.max() + pad
    # origin = projection of the world origin onto the plane
    origin = -n * (float(plane[3]) / float(np.dot(plane[:3], plane[:3])) ** 0.5)
    corners = np.array([
        origin + u * u0 + v * v0,
        origin + u * u1 + v * v0,
        origin + u * u1 + v * v1,
        origin + u * u0 + v * v1,
    ])
    poly = clip_convex_polygon(corners, bound_planes)
    if len(poly) == 0:
        return poly, np.zeros((0, 2))
    rel = poly - origin
    uv = np.stack([rel @ u, rel @ v], axis=1)
    return poly, uv


def fan_triangulate(poly):
    """Index-free triangle list for a convex polygon (P,3) -> ((P-2)*3, 3)."""
    if len(poly) < 3:
        return np.zeros((0, 3))
    tri = []
    for i in range(1, len(poly) - 1):
        tri.extend([poly[0], poly[i], poly[i + 1]])
    return np.array(tri)


def project_range(points, normal):
    """(min, max) of dot(normal, p) over points; used for scrub ranges."""
    if len(points) == 0:
        return 0.0, 0.0
    d = np.asarray(points) @ normalize(normal)
    return float(d.min()), float(d.max())


# ---------------------------------------------------------------------------
# hatch / colour helpers (shared by the GPU code and the concept renderer)

ISO_ANGLE_STEPS = (0.0, 90.0, 0.0, 90.0, 30.0, 120.0)
ISO_PITCH_SCALE = (1.0, 1.0, 1.6, 1.6, 1.3, 1.3)


def hatch_for_index(i, base_angle_deg, pitch, vary):
    """ISO 128-50 style: neighbouring parts alternate hatch direction and then
    spacing, so touching sections never read as one."""
    if not vary:
        return base_angle_deg, pitch
    k = i % len(ISO_ANGLE_STEPS)
    return base_angle_deg + ISO_ANGLE_STEPS[k], pitch * ISO_PITCH_SCALE[k]


def palette_color(key):
    """Stable, distinct, mid-saturation colour for a name (sRGB 0-1)."""
    import colorsys
    import zlib
    h = (zlib.crc32(key.encode("utf-8")) % 360) / 360.0
    # golden-ratio spread on top of the hash keeps nearby names apart
    h = (h + 0.61803398875 * (len(key) % 7)) % 1.0
    r, g, b = colorsys.hls_to_rgb(h, 0.55, 0.45)
    return (r, g, b)
