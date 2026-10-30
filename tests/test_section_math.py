# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for the pure-numpy section math. Run with:  python -m pytest tests
(or plain `python tests/test_section_math.py`). No Blender needed."""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "crosscut"))
import section_math as sm  # noqa: E402


# ---------------------------------------------------------------- mesh helpers

def uv_sphere(radius, segments=48, rings=24, inward=False):
    verts = [(0, 0, radius)]
    for i in range(1, rings):
        th = np.pi * i / rings
        for j in range(segments):
            ph = 2 * np.pi * j / segments
            verts.append((radius * np.sin(th) * np.cos(ph),
                          radius * np.sin(th) * np.sin(ph),
                          radius * np.cos(th)))
    verts.append((0, 0, -radius))
    v = np.array(verts, dtype=np.float64)
    bottom = len(v) - 1
    tris = []
    for j in range(segments):
        tris.append((0, 1 + j, 1 + (j + 1) % segments))
    for i in range(rings - 2):
        r0 = 1 + i * segments
        r1 = r0 + segments
        for j in range(segments):
            a, b = r0 + j, r0 + (j + 1) % segments
            c, d = r1 + j, r1 + (j + 1) % segments
            tris.append((a, c, d))
            tris.append((a, d, b))
    last = 1 + (rings - 2) * segments
    for j in range(segments):
        tris.append((last + j, bottom, last + (j + 1) % segments))
    t = np.array(tris, dtype=np.int64)
    if inward:
        t = t[:, ::-1]
    return v, t


def hollow_sphere(r_out=40.0, r_in=25.0):
    vo, to = uv_sphere(r_out)
    vi, ti = uv_sphere(r_in, inward=True)
    return np.vstack([vo, vi]), np.vstack([to, ti + len(vo)])


def soup(verts, tris):
    """Unmerge every vertex, like a raw STL."""
    v = verts[tris].reshape(-1, 3)
    t = np.arange(len(v)).reshape(-1, 3)
    return v, t


def cube(size=10.0):
    h = size / 2
    v = np.array([[x, y, z] for x in (-h, h) for y in (-h, h) for z in (-h, h)], float)
    quads = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    t = []
    for a, b, c, d in quads:
        t += [(a, b, c), (a, c, d)]
    return v, np.array(t)


# ------------------------------------------------------------ parity raster

def parity_raster(fan, u, v, origin, res=160, extent=45.0):
    """Software stand-in for the GPU invert-blend pass: count, per pixel centre,
    how many fan triangles cover it, and keep the parity."""
    xs = np.linspace(-extent, extent, res)
    gx, gy = np.meshgrid(xs, xs)
    P = np.stack([gx.ravel(), gy.ravel()], 1)
    tri = fan.reshape(-1, 3, 3) - origin
    t2 = np.stack([tri @ u, tri @ v], -1)  # (K,3,2)
    acc = np.zeros(len(P), dtype=np.int64)
    a, b, c = t2[:, 0], t2[:, 1], t2[:, 2]

    def edge(p0, p1, q):
        return (p1[:, None, 0] - p0[:, None, 0]) * (q[None, :, 1] - p0[:, None, 1]) - \
               (p1[:, None, 1] - p0[:, None, 1]) * (q[None, :, 0] - p0[:, None, 0])
    for s in range(0, len(a), 256):
        sl = slice(s, s + 256)
        e0 = edge(a[sl], b[sl], P)
        e1 = edge(b[sl], c[sl], P)
        e2 = edge(c[sl], a[sl], P)
        inside = ((e0 >= 0) & (e1 >= 0) & (e2 >= 0)) | ((e0 <= 0) & (e1 <= 0) & (e2 <= 0))
        acc += inside.sum(0)
    return (acc % 2).reshape(res, res).astype(bool), gx, gy


# ------------------------------------------------------------------- tests

def test_hollow_sphere_equator_is_closed_annulus():
    v, t = hollow_sphere()
    plane = (0.0, 0.0, 1.0, 0.0)  # z = 0 runs exactly through a vertex ring
    seg = sm.section_segments(v, t, plane)
    assert len(seg) > 0
    assert sm.open_endpoint_count(seg) == 0
    r = np.linalg.norm(seg[..., :2], axis=-1)
    assert np.all((np.abs(r - 40) < 0.5) | (np.abs(r - 25) < 0.5))


def test_soup_mesh_still_watertight_at_odd_offsets():
    v, t = soup(*hollow_sphere())
    for z in (0.0, 3.3, -17.25, 24.999, 39.0):
        seg = sm.section_segments(v, t, (0.0, 0.0, 1.0, -z))
        assert sm.open_endpoint_count(seg) == 0, z


def test_tilted_plane_closed():
    v, t = hollow_sphere()
    n = sm.normalize([0.3, -0.5, 0.8])
    seg = sm.section_segments(v, t, sm.plane_from_point_normal([1, 2, 3], n))
    assert sm.open_endpoint_count(seg) == 0


def test_open_mesh_detected():
    v, t = cube()
    t = np.delete(t, [4, 5], axis=0)  # delete the -Y face -> open box
    seg = sm.section_segments(v, t, (1.0, 0.0, 0.0, 0.0))
    assert sm.open_endpoint_count(seg) > 0


def test_cube_face_coplanar_cut_is_closed():
    v, t = cube()
    # cut exactly on the top face plane
    seg = sm.section_segments(v, t, (0.0, 0.0, 1.0, -5.0))
    assert sm.open_endpoint_count(seg) == 0


def test_even_odd_fill_matches_annulus():
    v, t = hollow_sphere()
    plane = np.array([0.0, 0.0, 1.0, -7.0])
    seg = sm.section_segments(v, t, plane)
    fan = sm.fan_triangles(seg, apex=np.array([31.0, -12.0, 7.0]))  # off-centre apex on purpose
    u, w = sm.plane_basis(plane[:3])
    mask, gx, gy = parity_raster(fan.astype(np.float64), u, w, np.array([0, 0, 7.0]))
    r = np.hypot(gx, gy)
    ro = np.sqrt(40**2 - 7**2)
    ri = np.sqrt(25**2 - 7**2)
    sure_in = (r < ro - 1.5) & (r > ri + 1.5)
    sure_out = (r > ro + 0.5) | (r < ri - 0.5)
    assert mask[sure_in].mean() > 0.995
    assert mask[sure_out].mean() < 0.005


def test_plane_to_local_roundtrip():
    rng = np.random.default_rng(1)
    m = np.eye(4)
    m[:3, :3] = rng.normal(size=(3, 3))
    m[:3, 3] = rng.normal(size=3) * 10
    plane = sm.plane_from_point_normal([1, 2, 3], [0.2, 0.9, -0.1])
    local = sm.plane_to_local(plane, m)
    p_local = rng.normal(size=(20, 3)) * 5
    p_world = sm.transform_points(p_local, m)
    np.testing.assert_allclose(p_world @ plane[:3] + plane[3], p_local @ local[:3] + local[3], atol=1e-9)


def test_clip_convex_polygon_and_cap_polygon():
    v, t = hollow_sphere()
    plane = np.array([0.0, 0.0, 1.0, 0.0])
    seg = sm.section_segments(v, t, plane)
    poly, uv = sm.cap_polygon(seg, plane, bound_planes=[(1.0, 0.0, 0.0, 0.0)])
    assert len(poly) >= 3
    assert np.all(poly[:, 0] >= -1e-9)
    assert np.allclose(poly[:, 2], 0.0)
    poly2, _ = sm.cap_polygon(seg, plane, bound_planes=[sm.CLIP_ALL])
    assert len(poly2) == 0


def test_bbox_crosses_plane():
    assert sm.bbox_crosses_plane(np.array([-1, -1, -1.]), np.array([1, 1, 1.]), (0, 0, 1, 0))
    assert not sm.bbox_crosses_plane(np.array([-1, -1, 2.]), np.array([1, 1, 3.]), (0, 0, 1, 0))


def test_hatch_for_index_alternates():
    a0, p0 = sm.hatch_for_index(0, 45, 8, True)
    a1, p1 = sm.hatch_for_index(1, 45, 8, True)
    assert a0 != a1 and p0 == p1
    assert sm.hatch_for_index(3, 45, 8, False) == (45, 8)


def test_close_open_contours():
    # a U-shaped (open) square contour gets its missing side back
    sq = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]], dtype=np.float64)
    u = np.array([[sq[0], sq[1]], [sq[1], sq[2]], [sq[2], sq[3]]])
    assert sm.open_endpoint_count(u) == 2
    closed = sm.close_open_contours(u)
    assert len(closed) == 4 and sm.open_endpoint_count(closed) == 0
    full = np.concatenate([u, [[sq[3], sq[0]]]])
    assert sm.close_open_contours(full) is full


def test_clip_segments():
    seg = np.array([[[-2.0, 0, 0], [2.0, 0, 0]], [[5.0, 1, 0], [6.0, 1, 0]], [[0.0, 2, 0], [1.0, 2, 0]]])
    keep_x_le_1 = np.array([-1.0, 0, 0, 1.0])
    out = sm.clip_segments(seg, [keep_x_le_1, sm.CLIP_NONE])
    assert len(out) == 2
    assert np.allclose(out[0], [[-2, 0, 0], [1, 0, 0]])
    assert np.allclose(out[1], seg[2])
    assert len(sm.clip_segments(seg, [sm.CLIP_ALL])) == 0


def test_box_section_polygon():
    z = np.array([0, 0, 1.0, -0.5])        # plane z = 0.5
    poly = sm.box_section_polygon(z, (0, 0, 0), (1, 1, 1))
    assert len(poly) == 4 and np.allclose(poly[:, 2], 0.5)
    assert np.allclose(poly.min(0)[:2], 0) and np.allclose(poly.max(0)[:2], 1)
    assert len(sm.box_section_polygon(np.array([0, 0, 1.0, -2.0]), (0, 0, 0), (1, 1, 1))) == 0


def test_clipped_box_faces():
    # unit box filled up to z = 0.25 (kept side: -z + 0.25 >= 0)
    faces = sm.clipped_box_faces((0, 0, 0), (1, 1, 1), [np.array([0, 0, -1.0, 0.25])])
    assert len(faces) == 6                              # bottom, 4 sides, the surface on the plane
    tops = [f for f in faces if f[2] == 0]
    assert len(tops) == 1 and np.allclose(tops[0][0][:, 2], 0.25) and np.allclose(tops[0][1], (0, 0, 1))
    for poly, n, _cut in faces:                         # all on or below the plane, outward-wound
        assert poly[:, 2].max() <= 0.25 + 1e-9
        assert np.dot(np.cross(poly[1] - poly[0], poly[2] - poly[0]), n) > 0
    # a plane below the box leaves nothing
    assert sm.clipped_box_faces((0, 0, 0), (1, 1, 1), [np.array([0, 0, -1.0, -0.5])]) == []


def test_section_segments_with_cached_columns():
    v = np.array([[0, 0, -1], [1, 0, 1], [0, 1, 1], [1, 1, -1]], dtype=np.float64)
    t = np.array([[0, 1, 2], [1, 3, 2]])
    plane = np.array([0, 0, 1.0, 0])
    cols = tuple(np.ascontiguousarray(t[:, i]) for i in range(3))
    assert np.array_equal(sm.section_segments(v, t, plane), sm.section_segments(v, t, plane, cols))


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
