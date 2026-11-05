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


def section_segments(verts, tris, plane, cols=None, crossings=False):
    """Intersect a triangle mesh with a plane.

    verts: (N, 3) float, tris: (M, 3) int, plane: 4-vector in the same space.
    Returns (K, 2, 3) float64 segment endpoints, each segment running
    counter-clockwise around the material when seen from the plane's normal side
    (given outward triangle normals), so contours can be filled by winding number.

    Watertightness: every crossing edge is evaluated with its endpoints in a
    canonical (lexicographic by coordinate) order, so two triangles sharing an
    edge produce bit-identical points, even when the mesh is a triangle soup
    with duplicated vertices. Vertices exactly on the plane count as "kept"
    (>= 0), which gives a consistent half-open classification: each triangle has
    exactly 0 or 2 crossing edges.

    cols: optional (tris[:, 0], tris[:, 1], tris[:, 2]) as contiguous arrays,
    cached by the caller; makes the crossing test about 4x faster.
    crossings: also return what crossing_values needs to carry a per-corner
    value (a UV, say) along each segment: (segments, crossings).
    """
    verts = np.asarray(verts, dtype=np.float64)
    tris = np.asarray(tris, dtype=np.int64)
    none = np.zeros((0, 2, 3))
    if len(tris) == 0:
        return (none, None) if crossings else none
    s = verts @ np.asarray(plane[:3], dtype=np.float64) + float(plane[3])
    pos = s >= 0.0
    if cols is None:
        cols = (tris[:, 0], tris[:, 1], tris[:, 2])
    p0, p1, p2 = pos[cols[0]], pos[cols[1]], pos[cols[2]]
    keep = (p0 != p1) | (p1 != p2)
    if not keep.any():
        return (none, None) if crossings else none
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
    seg = p.reshape(-1, 2, 3)
    normals = np.cross(verts[tm[:, 1]] - verts[tm[:, 0]], verts[tm[:, 2]] - verts[tm[:, 0]])
    tangents = np.cross(np.asarray(plane[:3], dtype=np.float64), normals)
    backwards = np.einsum("ij,ij->i", seg[:, 1] - seg[:, 0], tangents) < 0.0
    seg[backwards] = seg[backwards][:, ::-1]
    if crossings:
        info = {"tri": np.flatnonzero(keep), "corner": np.nonzero(cross)[1].reshape(-1, 2),
                "t": t.reshape(-1, 2), "swap": swap.reshape(-1, 2), "backwards": backwards}
        return seg, info
    return seg


def crossing_values(info, corners):
    """A per-corner value at both ends of each segment from section_segments(crossings=True).
    corners: (M, 3, D), one value per triangle corner. Returns (K, 2, D)."""
    c = np.asarray(corners)[info["tri"]]
    row = np.arange(len(c))[:, None]
    a = c[row, info["corner"]]
    b = c[row, (info["corner"] + 1) % 3]
    swap = info["swap"][..., None]
    a, b = np.where(swap, b, a), np.where(swap, a, b)
    out = a + info["t"][..., None] * (b - a)
    out[info["backwards"]] = out[info["backwards"]][:, ::-1]
    return out


def shell_inward(seg, normal, flip=False):
    """Which way is inward at both ends of each segment (K, 2, 3). Segments run counter-clockwise
    around the material seen from `normal`, so inward is on their left (`flip` for a mirrored or
    inside-out part). Segments meeting at a point share one direction, weighted by length, so a
    band along a finely faceted contour has no cracks."""
    d = seg[:, 1] - seg[:, 0]
    per_seg = np.cross(np.asarray(normal, dtype=np.float64), d)  # its length is the segment's
    if flip:
        per_seg = -per_seg
    _pts, ids = np.unique(seg.reshape(-1, 3), axis=0, return_inverse=True)
    ids = ids.reshape(-1)
    summed = np.zeros((int(ids.max()) + 1, 3)) if len(ids) else np.zeros((0, 3))
    np.add.at(summed, ids, np.repeat(per_seg, 2, axis=0))
    out = summed[ids].reshape(-1, 2, 3)
    # a contour doubling back on itself cancels out: fall back on the segment's own
    size = np.linalg.norm(out, axis=2, keepdims=True)
    own = per_seg[:, None, :] / np.maximum(np.linalg.norm(per_seg, axis=1), 1e-300)[:, None, None]
    return np.where(size > 1e-12, out / np.maximum(size, 1e-300), own)


def shell_quads(seg, inward, centered=False):
    """Two triangles per segment for a band along a contour: (pos, inward, side), per vertex, where
    a vertex belongs at pos + inward * side * width. inward: from shell_inward. `centered`
    straddles the contour, for a part whose inside isn't known."""
    side = np.array([0.0, 0.0, 1.0, 0.0, 1.0, 1.0])
    if centered:
        side = side - 0.5
    return repeat_for_shell(seg), repeat_for_shell(inward), np.tile(side, len(seg))


def repeat_for_shell(values):
    """Per-end values (K, 2, D) laid out as shell_quads' vertices."""
    return values[:, np.array([0, 1, 1, 0, 1, 0])].reshape(-1, values.shape[2])


def open_endpoint_count(segments):
    """Number of segment endpoints that are not shared by an even number of
    segments. Zero means every contour is closed (watertight cross-section)."""
    if len(segments) == 0:
        return 0
    pts = np.ascontiguousarray(segments.reshape(-1, 3))
    keys = pts.view(np.dtype((np.void, pts.dtype.itemsize * 3))).ravel()
    _, counts = np.unique(keys, return_counts=True)
    return int(np.count_nonzero(counts % 2))


def mesh_edge_state(verts, tris):
    """(open, oriented). Open: an edge is used by an odd number of triangles, so
    the mesh does not enclose a volume. Oriented: closed, and every edge is used
    as often in each direction, so its normals agree and contours can be filled
    by winding number. Vertices are matched by exact position, as in
    open_endpoint_count: unwelded but touching shells still count as closed."""
    if len(tris) == 0:
        return False, True
    pts = np.ascontiguousarray(verts)
    keys = pts.view(np.dtype((np.void, pts.dtype.itemsize * 3))).ravel()
    _, ids = np.unique(keys, return_inverse=True)
    ids = ids.reshape(-1)[tris]
    a = np.concatenate([ids[:, 0], ids[:, 1], ids[:, 2]])
    b = np.concatenate([ids[:, 1], ids[:, 2], ids[:, 0]])
    keep = a != b
    a, b = a[keep], b[keep]
    edges = np.minimum(a, b) * (len(pts) + 1) + np.maximum(a, b)
    _, inverse, counts = np.unique(edges, return_inverse=True, return_counts=True)
    is_open = bool(np.any(counts % 2))
    balance = np.bincount(inverse.reshape(-1), weights=np.where(a < b, 1.0, -1.0))
    return is_open, not is_open and not np.any(balance)


def mesh_signed_volume(verts, tris):
    """Volume enclosed by the triangles; negative when the mesh is inside out."""
    v = np.asarray(verts, dtype=np.float64)
    a, b, c = v[tris[:, 0]], v[tris[:, 1]], v[tris[:, 2]]
    o = v.mean(0) if len(v) else np.zeros(3)  # around the mesh, for an open mesh's sake
    return float(np.einsum("ij,ij->i", a - o, np.cross(b - o, c - o)).sum()) / 6.0


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


def clipped_box_faces(lo, hi, planes):
    """Faces of the axis-aligned box [lo, hi] cut down to the kept side of
    every plane (a convex solid). Returns [(poly (P,3), outward normal (3,), cut)],
    where cut is the index of the plane a face lies on, or -1 for a box side."""
    lo = np.asarray(lo, dtype=np.float64)
    hi = np.asarray(hi, dtype=np.float64)
    x0, y0, z0 = lo
    x1, y1, z1 = hi
    sides = [  # counter-clockwise seen from outside
        ([(x0, y0, z0), (x0, y1, z0), (x1, y1, z0), (x1, y0, z0)], (0, 0, -1)),
        ([(x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)], (0, 0, 1)),
        ([(x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1)], (0, -1, 0)),
        ([(x0, y1, z0), (x0, y1, z1), (x1, y1, z1), (x1, y1, z0)], (0, 1, 0)),
        ([(x0, y0, z0), (x0, y0, z1), (x0, y1, z1), (x0, y1, z0)], (-1, 0, 0)),
        ([(x1, y0, z0), (x1, y1, z0), (x1, y1, z1), (x1, y0, z1)], (1, 0, 0)),
    ]
    planes = [np.asarray(p, dtype=np.float64) for p in planes if not plane_is_degenerate(p)]
    out = []
    for poly, n in sides:
        q = clip_convex_polygon(np.array(poly, dtype=np.float64), planes)
        if len(q) >= 3:
            out.append((q, np.array(n, dtype=np.float64), -1))
    for i, pl in enumerate(planes):
        q = box_section_polygon(pl, lo, hi)
        q = clip_convex_polygon(q, [p for j, p in enumerate(planes) if j != i]) if len(q) else q
        if len(q) < 3:
            continue
        n = -normalize(pl[:3])  # the kept side is n.p + d >= 0, so outward is -n
        if np.dot(np.cross(q[1] - q[0], q[2] - q[0]), n) < 0:
            q = q[::-1]
        out.append((q, n, i))
    return out


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


def _mm2(data):
    """Blender's BLI_hash_mm2, seed 0."""
    m, n, i = 0x5bd1e995, len(data), 0
    h = n & 0xffffffff
    while n >= 4:
        k = (int.from_bytes(data[i:i + 4], "little") * m) & 0xffffffff
        k = ((k ^ (k >> 24)) * m) & 0xffffffff
        h = ((h * m) & 0xffffffff) ^ k
        i, n = i + 4, n - 4
    if n == 3:
        h ^= data[i + 2] << 16
    if n >= 2:
        h ^= data[i + 1] << 8
    if n >= 1:
        h = ((h ^ data[i]) * m) & 0xffffffff
    h = ((h ^ (h >> 13)) * m) & 0xffffffff
    return h ^ (h >> 15)


def _hash_int(k):
    """Blender's BLI_hash_int."""
    def rot(x, s):
        return ((x << s) | (x >> (32 - s))) & 0xffffffff
    a = b = c = (0xdeadbeef + (2 << 2) + 13) & 0xffffffff
    a = (a + k) & 0xffffffff
    c = ((c ^ b) - rot(b, 14)) & 0xffffffff
    a = ((a ^ c) - rot(c, 11)) & 0xffffffff
    b = ((b ^ a) - rot(a, 25)) & 0xffffffff
    c = ((c ^ b) - rot(b, 16)) & 0xffffffff
    a = ((a ^ c) - rot(c, 4)) & 0xffffffff
    b = ((b ^ a) - rot(a, 14)) & 0xffffffff
    c = ((c ^ b) - rot(b, 24)) & 0xffffffff
    return c


def random_shading_color(name, library_path=None):
    """The colour Solid shading's Random mode gives an object of this name
    (scene-linear), worked out the way Blender does."""
    import colorsys
    h = _mm2(b"OB" + name.encode("utf-8") + b"\0")
    if library_path:
        h = ((h * 13) & 0xffffffff) ^ _mm2(library_path.encode("utf-8") + b"\0")
    return colorsys.hsv_to_rgb(_hash_int(h) / 0xffffffff, 0.5, 0.8)


def _inside_rows(seg, oriented, xs, ys):
    """Which cells of the grid (ys, xs) lie inside the contours `seg` (K,2,2):
    nonzero winding if oriented, else even-odd."""
    ax, ay, bx, by = seg[:, 0, 0], seg[:, 0, 1], seg[:, 1, 0], seg[:, 1, 1]
    grid = np.zeros((len(ys), len(xs)), dtype=bool)
    for j, y in enumerate(ys):
        hit = np.nonzero((ay > y) != (by > y))[0]
        if not len(hit):
            continue
        x_at = ax[hit] + (y - ay[hit]) * (bx[hit] - ax[hit]) / (by[hit] - ay[hit])
        w = np.zeros(len(xs) + 1)
        step = np.where(by[hit] > ay[hit], 1.0, -1.0) if oriented else np.ones(len(hit))
        np.add.at(w, np.searchsorted(xs, x_at), step)
        total = np.cumsum(w)[:len(xs)]
        grid[j] = total != 0 if oriented else total % 2 == 1
    return grid


def _flood(mask, j, i):
    """The 4-connected part of the boolean grid `mask` containing cell (j, i)."""
    out = np.zeros_like(mask)
    out[j, i] = True
    while True:
        grown = out.copy()
        grown[1:] |= out[:-1]
        grown[:-1] |= out[1:]
        grown[:, 1:] |= out[:, :-1]
        grown[:, :-1] |= out[:, 1:]
        grown &= mask
        if np.array_equal(grown, out):
            return out
        out = grown


def _samples(seg, step, limit=4000):
    """Points along segments (K,2,2) about `step` apart: (points (P,2), segment index (P,))."""
    d = seg[:, 1] - seg[:, 0]
    n = np.minimum(np.ceil(np.hypot(d[:, 0], d[:, 1]) / max(step, 1e-12)).astype(np.int64), 256) + 1
    if n.sum() > limit:
        n = np.maximum((n * limit / n.sum()).astype(np.int64), 2)
    idx = np.repeat(np.arange(len(seg)), n)
    t = np.concatenate([np.linspace(0.0, 1.0, k) for k in n]) if len(seg) else np.zeros(0)
    return seg[idx, 0] + d[idx] * t[:, None], idx


def _farthest(points, seg):
    """(distance, point, nearest point on seg) for whichever of `points` is
    farthest from the segments (K,2,2), measured to the nearest of them."""
    a = seg[:, 0]
    d = seg[:, 1] - a
    dd = np.maximum(np.einsum("ij,ij->i", d, d), 1e-30)
    rel = points[:, None, :] - a[None, :, :]
    t = np.clip(np.einsum("pkj,kj->pk", rel, d) / dd, 0.0, 1.0)
    near = a[None, :, :] + t[:, :, None] * d[None, :, :]
    dist = np.linalg.norm(points[:, None, :] - near, axis=2)
    k = dist.argmin(axis=1)
    p = int(dist[np.arange(len(points)), k].argmax())
    return float(dist[p, k[p]]), points[p], near[p, k[p]]


def _chord(sa, sb, point, angles=60, around=None):
    """The shortest line through `point` from one part's contour to the other's
    (or between any two contours if no such line exists): (length, end, end).
    With `around`, only lines within 15 degrees of that direction (radians)."""
    seg = np.concatenate([sa, sb])
    part = np.concatenate([np.zeros(len(sa), dtype=bool), np.ones(len(sb), dtype=bool)])
    a = seg[:, 0] - point
    e = seg[:, 1] - seg[:, 0]
    th = np.linspace(0.0, np.pi, angles, endpoint=False) if around is None else around + np.radians(np.linspace(-15.0, 15.0, 11))
    angles = len(th)
    dx, dy = np.cos(th)[:, None], np.sin(th)[:, None]
    with np.errstate(divide='ignore', invalid='ignore'):
        denom = dx * e[:, 1] - dy * e[:, 0]
        t = (a[:, 0] * e[:, 1] - a[:, 1] * e[:, 0]) / denom
        u = (a[:, 0] * dy - a[:, 1] * dx) / denom
    ok = np.isfinite(t) & (u >= 0.0) & (u <= 1.0)
    ahead = np.where(ok & (t > 0.0), t, np.inf)
    behind = np.where(ok & (t < 0.0), -t, np.inf)
    i_a, i_b = ahead.argmin(axis=1), behind.argmin(axis=1)
    rows = np.arange(angles)
    ta, tb = ahead[rows, i_a], behind[rows, i_b]
    length = ta + tb
    if not np.isfinite(length).any():
        return None
    across = np.isfinite(length) & (part[i_a] != part[i_b])
    k = int(np.where(across, length, np.inf).argmin()) if across.any() else int(np.nan_to_num(length, posinf=1e300).argmin())
    d = np.array([dx[k, 0], dy[k, 0]])
    return float(length[k]), point + d * ta[k], point - d * tb[k]


def overlap_span(seg_a, seg_b, point, oriented=(True, True), half=1.0, cells=160, limit=2000):
    """The overlap's greatest depth: (distance, end, end), or None. See overlap_measures."""
    return overlap_measures(seg_a, seg_b, point, oriented, half, cells, limit, local=False)[0]


def overlap_measures(seg_a, seg_b, point, oriented=(True, True), half=1.0, cells=160, limit=2000, local=True):
    """How deep two parts' sections overlap at `point` (all 2D, in the plane).

    Finds the overlap island under the point on a grid that grows until it holds
    the whole island. Returns (greatest, local): `greatest` is the greatest
    distance from the island's boundary on one part's contour to its boundary on
    the other's, `local` the shortest line through the point from one contour to
    the other, roughly tangent to tangent. Each is (distance, end, end) or None;
    both are None when the point isn't inside both. A very long, thin island can
    break up on the grid, and then only the piece under the point is measured.
    """
    if not len(seg_a) or not len(seg_b):
        return None, None
    px, py = float(point[0]), float(point[1])
    all_pts = np.concatenate([seg_a.reshape(-1, 2), seg_b.reshape(-1, 2)])
    most = float(np.abs(all_pts - (px, py)).max()) * 1.01 + 1e-9
    half = min(half, most)
    while True:
        xs = np.linspace(px - half, px + half, cells)
        ys = np.linspace(py - half, py + half, cells)
        both = _inside_rows(seg_a, oriented[0], xs, ys) & _inside_rows(seg_b, oriented[1], xs, ys)
        j = i = cells // 2
        if not both[j, i]:
            near = np.argwhere(both[j - 1:j + 2, i - 1:i + 2])
            if not len(near):
                return None, None
            j, i = j - 1 + near[0][0], i - 1 + near[0][1]
        island = _flood(both, j, i)
        at_edge = island[0].any() or island[-1].any() or island[:, 0].any() or island[:, -1].any()
        if not at_edge or half >= most:
            break
        half = min(half * 2.0, most)
    cell = xs[1] - xs[0]
    wide = island.copy()  # contours run along the island's edge cells
    for _ in range(2):
        grown = wide.copy()
        grown[1:] |= wide[:-1]
        grown[:-1] |= wide[1:]
        grown[:, 1:] |= wide[:, :-1]
        grown[:, :-1] |= wide[:, 1:]
        wide = grown

    def on_island(seg):
        # only segments that can reach the window, so samples stay fine-grained
        lo, hi = seg.min(axis=1), seg.max(axis=1)
        keep = (hi[:, 0] >= xs[0]) & (lo[:, 0] <= xs[-1]) & (hi[:, 1] >= ys[0]) & (lo[:, 1] <= ys[-1])
        s = seg[keep]
        if not len(s):
            return np.zeros((0, 2)), s
        pts, idx = _samples(s, cell)
        ci = np.round((pts[:, 0] - xs[0]) / cell).astype(np.int64)
        cj = np.round((pts[:, 1] - ys[0]) / cell).astype(np.int64)
        ok = (ci >= 0) & (ci < cells) & (cj >= 0) & (cj < cells)
        ok[ok] = wide[cj[ok], ci[ok]]
        return pts[ok], s[np.unique(idx[ok])]

    pa, sa = on_island(seg_a)
    pb, sb = on_island(seg_b)
    if not len(pa) and not len(pb):
        return None, None
    # one part wholly inside the other: the island's edge is all one contour
    if not len(sa):
        sa = seg_a
    if not len(sb):
        sb = seg_b
    best = None
    for pts, other in ((pa, sb), (pb, sa)):
        if len(pts) and len(other):
            pts = pts[:: max(1, len(pts) // limit)]
            other = other[:: max(1, len(other) // limit)]
            r = _farthest(pts, other)
            if best is None or r[0] > best[0]:
                best = r
    near = _chord(sa, sb, np.array([px, py], dtype=np.float64)) if local else None
    return best, near


def snap_to_contour(seg, target, avoid=None, radius=0.0):
    """The point on the contours (K,2,2) nearest `target`, leaving out segments that pass
    within `radius` of `avoid` (the wall a measuring line is anchored on), if any remain."""
    if avoid is not None and radius > 0.0:
        a = seg[:, 0]
        d = seg[:, 1] - a
        t = np.clip(np.einsum("ij,ij->i", avoid - a, d) / np.maximum(np.einsum("ij,ij->i", d, d), 1e-30), 0.0, 1.0)
        away = np.linalg.norm(a + t[:, None] * d - avoid, axis=1) > radius
        if away.any():
            seg = seg[away]
    return _farthest(np.asarray(target, dtype=np.float64)[None, :], seg)[2]


def follow_cursor(seg, anchor, cursor, oriented=False, radius=0.0):
    """Where the free end of a line anchored at `anchor` goes, for the mouse at `cursor`.
    Inside the section: the line runs through the cursor to the first contour beyond it,
    so the cursor is always on the line. Outside: the nearest point on the contours."""
    cursor = np.asarray(cursor, dtype=np.float64)
    inside = _inside_rows(seg, oriented, np.array([cursor[0]]), np.array([cursor[1]]))[0, 0]
    d = cursor - anchor
    length = float(np.hypot(d[0], d[1]))
    if inside and length > 1e-12:
        d = d / length
        a = seg[:, 0] - anchor
        e = seg[:, 1] - seg[:, 0]
        with np.errstate(divide='ignore', invalid='ignore'):
            denom = d[0] * e[:, 1] - d[1] * e[:, 0]
            t = (a[:, 0] * e[:, 1] - a[:, 1] * e[:, 0]) / denom
            u = (a[:, 0] * d[1] - a[:, 1] * d[0]) / denom
        ahead = np.isfinite(t) & (u >= 0.0) & (u <= 1.0) & (t >= length * (1.0 - 1e-9))
        if ahead.any():
            return anchor + d * float(t[ahead].min())
    return snap_to_contour(seg, cursor, anchor, radius)


def anchor_normals(contours, anchor):
    """The unit normals of the contour segments an anchor sits on: one mid-segment, two at a corner."""
    anchor = np.asarray(anchor, dtype=np.float64)
    best, found = float("inf"), []
    for seg in contours:
        if not len(seg):
            continue
        d = seg[:, 1] - seg[:, 0]
        len2 = np.maximum(np.einsum("ij,ij->i", d, d), 1e-300)
        t = np.clip(np.einsum("ij,ij->i", anchor - seg[:, 0], d) / len2, 0.0, 1.0)
        dist = np.linalg.norm(seg[:, 0] + d * t[:, None] - anchor, axis=1)
        low = float(dist.min())
        tie = np.flatnonzero(dist <= low + 1e-6 * max(low, float(np.sqrt(len2.max())), 1e-9))
        if low < best - 1e-9:
            best, found = low, []
        if low <= best + 1e-9:
            found.extend(np.stack([-d[tie, 1], d[tie, 0]], axis=1) / np.sqrt(len2[tie])[:, None])
    out = []
    for n in found:
        if not any(abs(float(n @ m)) > 1.0 - 1e-9 for m in out):
            out.append(n)
    return out


def snap_normal(seg, anchor, normals, cursor, oriented, tol):
    """Where the free end goes if the line snaps straight out from the anchor's contour, or None
    if the cursor isn't within `tol` of one of those lines. Returns (end, direction). Past the
    cursor inside the section, as follow_cursor; otherwise the crossing nearest the cursor."""
    cursor = np.asarray(cursor, dtype=np.float64)
    d = cursor - anchor
    if float(np.hypot(d[0], d[1])) <= 2.0 * tol:  # this close, any direction is within reach of a normal
        return None
    best = None
    for n in normals:
        along = float(d @ n)
        m, along = (n, along) if along >= 0.0 else (-n, -along)
        off = float(np.linalg.norm(d - m * along))
        if off <= tol and (best is None or off < best[0]):
            best = (off, m, along)
    if best is None:
        return None
    _off, m, along = best
    a = seg[:, 0] - anchor
    e = seg[:, 1] - seg[:, 0]
    with np.errstate(divide='ignore', invalid='ignore'):
        denom = m[0] * e[:, 1] - m[1] * e[:, 0]
        t = (a[:, 0] * e[:, 1] - a[:, 1] * e[:, 0]) / denom
        u = (a[:, 0] * m[1] - a[:, 1] * m[0]) / denom
    t = t[np.isfinite(t) & (u >= 0.0) & (u <= 1.0) & (t > 1e-6 * max(along, 1e-3))]
    if not len(t):
        return None
    foot = anchor + m * along
    if _inside_rows(seg, oriented, np.array([foot[0]]), np.array([foot[1]]))[0, 0]:
        beyond = t[t >= along]
        if len(beyond):
            return anchor + m * float(beyond.min()), m
    return anchor + m * float(t[np.argmin(np.abs(t - along))]), m


def section_measures(seg, point, oriented=True, half=1.0, cells=160, local=True, greatest=False):
    """How thick one part's section is at `point` (all 2D, in the plane): (greatest,
    local), each (distance, end, end) or None. `local` is the shortest line through
    the point across the section, within 15 degrees of straight across from the nearest wall. `greatest` is the same at the island's thickest
    place: where eroding it from the outside lasts longest."""
    if not len(seg):
        return None, None
    p = np.array(point, dtype=np.float64)
    pts = seg.reshape(-1, 2)
    most = float(np.abs(pts - p).max()) * 1.01 + 1e-9
    lo, hi = seg.min(axis=1), seg.max(axis=1)

    def chord_at(c):
        h = min(half, most)
        while True:
            keep = (hi[:, 0] >= c[0] - h) & (lo[:, 0] <= c[0] + h) & (hi[:, 1] >= c[1] - h) & (lo[:, 1] <= c[1] + h)
            r = None
            if keep.any():
                # straight across from the nearest wall: a line left free to be shortest cuts corners
                d, _c, q = _farthest(c[None, :], seg[keep])
                if d <= h or h >= most:
                    away = c - q
                    around = float(np.arctan2(away[1], away[0])) if d > 1e-12 else 0.0
                    r = _chord(seg[keep], np.zeros((0, 2, 2)), c, around=around)
            # only trust a line that ended inside the segments looked at
            if h >= most or (r is not None and max(np.abs(r[1] - c).max(), np.abs(r[2] - c).max()) <= h):
                return r
            h = min(h * 2.0, most)

    near = chord_at(p) if local else None
    if not greatest:
        return None, near
    h = min(half, most)
    while True:
        xs = np.linspace(p[0] - h, p[0] + h, cells)
        ys = np.linspace(p[1] - h, p[1] + h, cells)
        inside = _inside_rows(seg, oriented, xs, ys)
        j = i = cells // 2
        if not inside[j, i]:
            return None, near
        island = _flood(inside, j, i)
        if h >= most or not (island[0].any() or island[-1].any() or island[:, 0].any() or island[:, -1].any()):
            break
        h = min(h * 2.0, most)
    core = island
    while True:
        shrunk = core.copy()
        shrunk[1:] &= core[:-1]
        shrunk[:-1] &= core[1:]
        shrunk[:, 1:] &= core[:, :-1]
        shrunk[:, :-1] &= core[:, 1:]
        shrunk[0] = shrunk[-1] = False
        shrunk[:, 0] = shrunk[:, -1] = False
        if not shrunk.any():
            break
        core = shrunk
    cells_left = np.argwhere(core)
    cj, ci = cells_left[np.abs(cells_left - cells_left.mean(axis=0)).sum(axis=1).argmin()]
    return chord_at(np.array([xs[ci], ys[cj]])), near


def palette_color(key):
    """Stable, distinct, mid-saturation colour for a name (sRGB 0-1)."""
    import colorsys
    import zlib
    h = (zlib.crc32(key.encode("utf-8")) % 360) / 360.0
    # golden-ratio spread on top of the hash keeps nearby names apart
    h = (h + 0.61803398875 * (len(key) % 7)) % 1.0
    r, g, b = colorsys.hls_to_rgb(h, 0.55, 0.45)
    return (r, g, b)
