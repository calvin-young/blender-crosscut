# SPDX-License-Identifier: GPL-3.0-or-later
"""Concept renders of Crosscut's display options, made WITHOUT Blender.

A tiny numpy ray caster that mimics the add-on's rules (clip planes, caps drawn
where the plane is inside a solid and nothing nearer survives clipping, screen
space hatching, interference where 2+ solids overlap). Used for the README's
"alternatives" figures. Real screenshots come from tools/showcase.py.

    python tools/concept_render.py  ->  docs/images/concepts/*.png
"""

import math
import os
import warnings

import numpy as np
from PIL import Image, ImageDraw, ImageFont

W, H = 520, 420
OUT = os.path.join(os.path.dirname(__file__), "..", "docs", "images", "concepts")
BG = np.array([0.24, 0.24, 0.24])
LIGHT = np.array([0.4, -0.6, 0.7])
LIGHT = LIGHT / np.linalg.norm(LIGHT)


# ------------------------------------------------------------------ camera

def camera(eye, target, fov=32.0):
    eye = np.array(eye, float)
    f = np.array(target, float) - eye
    f /= np.linalg.norm(f)
    r = np.cross(f, [0, 0, 1.0])
    r /= np.linalg.norm(r)
    u = np.cross(r, f)
    t = math.tan(math.radians(fov) / 2)
    ys, xs = np.mgrid[0:H, 0:W]
    px = (2 * (xs + 0.5) / W - 1) * t * W / H
    py = (1 - 2 * (ys + 0.5) / H) * t
    d = f[None, None] + px[..., None] * r + py[..., None] * u
    d /= np.linalg.norm(d, axis=-1, keepdims=True)
    return eye, d.reshape(-1, 3)


# --------------------------------------------------------------- primitives
# each surface: function(o, d) -> list of (t, normal) arrays; solid: inside(p)

class Sphere:
    def __init__(self, c, r, inward=False):
        self.c, self.r, self.inward = np.array(c, float), r, inward

    def hits(self, o, d):
        oc = o - self.c
        b = d @ oc
        cc = oc @ oc - self.r ** 2
        disc = b * b - cc
        ok = disc >= 0
        sq = np.sqrt(np.where(ok, disc, 0))
        out = []
        for t in (-b - sq, -b + sq):
            t = np.where(ok, t, np.inf)
            p = o + d * t[:, None]
            n = (p - self.c) / self.r
            if self.inward:
                n = -n
            out.append((t, n))
        return out


class Box:
    def __init__(self, c, size):
        self.c, self.h = np.array(c, float), np.array(size, float) / 2

    def hits(self, o, d):
        out = []
        with np.errstate(divide='ignore', invalid='ignore'):
            for ax in range(3):
                for sgn in (-1, 1):
                    plane = self.c[ax] + sgn * self.h[ax]
                    t = (plane - o[ax]) / d[:, ax]
                    p = o + d * t[:, None]
                    inside = np.ones(len(d), bool)
                    for k in range(3):
                        if k != ax:
                            inside &= np.abs(p[:, k] - self.c[k]) <= self.h[k]
                    t = np.where(inside & np.isfinite(t), t, np.inf)
                    n = np.zeros((len(d), 3))
                    n[:, ax] = sgn
                    out.append((t, n))
        return out

    def inside(self, p):
        return np.all(np.abs(p - self.c) <= self.h, axis=-1)


class CylZ:
    def __init__(self, c, r, depth):
        self.c, self.r, self.hz = np.array(c, float), r, depth / 2

    def hits(self, o, d):
        out = []
        oc = o - self.c
        a = d[:, 0] ** 2 + d[:, 1] ** 2
        b = d[:, 0] * oc[0] + d[:, 1] * oc[1]
        cc = oc[0] ** 2 + oc[1] ** 2 - self.r ** 2
        with np.errstate(divide='ignore', invalid='ignore'):
            disc = b * b - a * cc
            ok = disc >= 0
            sq = np.sqrt(np.where(ok, disc, 0))
            for t in ((-b - sq) / a, (-b + sq) / a):
                p = o + d * t[:, None]
                good = ok & (np.abs(p[:, 2] - self.c[2]) <= self.hz)
                n = np.stack([(p[:, 0] - self.c[0]) / self.r, (p[:, 1] - self.c[1]) / self.r, np.zeros(len(d))], 1)
                out.append((np.where(good, t, np.inf), n))
            for sgn in (-1, 1):
                z = self.c[2] + sgn * self.hz
                t = (z - o[2]) / d[:, 2]
                p = o + d * t[:, None]
                good = (p[:, 0] - self.c[0]) ** 2 + (p[:, 1] - self.c[1]) ** 2 <= self.r ** 2
                n = np.zeros((len(d), 3))
                n[:, 2] = sgn
                out.append((np.where(good & np.isfinite(t), t, np.inf), n))
        return out

    def inside(self, p):
        return ((p[:, 0] - self.c[0]) ** 2 + (p[:, 1] - self.c[1]) ** 2 <= self.r ** 2) & \
               (np.abs(p[:, 2] - self.c[2]) <= self.hz)


class HollowSphere:
    def __init__(self, c, ro, ri):
        self.o, self.i = Sphere(c, ro), Sphere(c, ri, inward=True)
        self.c, self.ro, self.ri = np.array(c, float), ro, ri

    def hits(self, o, d):
        return self.o.hits(o, d) + self.i.hits(o, d)

    def inside(self, p):
        r = np.linalg.norm(p - self.c, axis=-1)
        return (r <= self.ro) & (r >= self.ri)


# ------------------------------------------------------------------ render

def srgb(c):
    return np.clip(c, 0, 1)


def hatch_mask(pitch, angle_deg, width=0.3, cross=False):
    ys, xs = np.mgrid[0:H, 0:W]
    a = math.radians(angle_deg)
    x = (-math.sin(a) * xs + math.cos(a) * (H - ys)) / pitch
    d = np.abs((x + 0.5) % 1.0 - 0.5)
    m = np.clip((width / 2 + 0.06 - d) / 0.12, 0, 1)
    if cross:
        x2 = (math.cos(a) * xs + math.sin(a) * (H - ys)) / pitch
        d2 = np.abs((x2 + 0.5) % 1.0 - 0.5)
        m = np.maximum(m, np.clip((width / 2 + 0.06 - d2) / 0.12, 0, 1))
    return m.reshape(-1)


def render(objects, eye, target, clips=(), caps=(), style='HATCH', interference=True,
           vary=True, backface_tint=None, outline=True):
    """objects: list of (solid, color). clips: planes (n, d) kept where n.p + d >= 0.
    caps: planes to cap. style: BACKFACES | SOLID | HATCH."""
    o, d = camera(eye, target)
    npx = len(d)
    best_t = np.full(npx, np.inf)
    best_c = np.tile(BG, (npx, 1))
    for obj, col, *_cap in objects:
        for t, n in obj.hits(o, d):
            p = o + d * t[:, None]
            keep = np.isfinite(t) & (t > 1e-6)
            for pl in clips:
                keep &= (p @ pl[:3] + pl[3]) >= -1e-9
            closer = keep & (t < best_t)
            facing = np.einsum('ij,ij->i', n, -d)
            back = facing < 0
            shade_n = np.where(back[:, None], -n, n)
            lam = np.clip(np.einsum('ij,j->i', shade_n, LIGHT), 0, 1)
            c = np.array(col)[None] * (0.35 + 0.65 * lam[:, None])
            if backface_tint is not None:
                c = np.where(back[:, None], np.array(backface_tint)[None], c)
            elif style == 'BACKFACES':
                c = np.where(back[:, None], c * 0.85, c)
            best_t = np.where(closer, t, best_t)
            best_c = np.where(closer[:, None], c, best_c)
    edge = np.zeros(npx, bool)
    if style != 'BACKFACES' and backface_tint is None:
        for pl in caps:
            n_, dd = np.array(pl[:3]), pl[3]
            with np.errstate(divide='ignore', invalid='ignore'):
                tp = -(o @ n_ + dd) / (d @ n_)
            pp = o + d * tp[:, None]
            vis = np.isfinite(tp) & (tp > 0) & (tp <= best_t + 1e-6)
            for other in clips:
                if other is pl or not np.any(other[:3]):
                    continue
                vis &= (pp @ other[:3] + other[3]) >= -1e-6
            count = np.zeros(npx, int)
            for idx, (obj, col, *cap_col) in enumerate(objects):
                col = cap_col[0] if cap_col else col
                ins = obj.inside(pp) & vis
                count += ins
                if not ins.any():
                    continue
                fill = np.array(col)[None].repeat(npx, 0)
                if style == 'HATCH':
                    ang = 45 + (90 if (vary and idx % 2) else 0)
                    pitch = 10 * (1.6 if (vary and (idx // 2) % 2) else 1.0)
                    m = hatch_mask(pitch, ang)[:, None]
                    fill = fill * (1 - m) + fill * 0.18 * m
                best_c = np.where(ins[:, None], fill, best_c)
                # contour: inside-mask boundary
                img = ins.reshape(H, W)
                e = img ^ np.roll(img, 1, 0) | img ^ np.roll(img, 1, 1)
                edge |= e.reshape(-1) & vis
            if interference:
                inter = count >= 2
                if inter.any():
                    m = hatch_mask(10, 45, 0.25, cross=True)[:, None]
                    red = np.array([0.86, 0.10, 0.08])[None]
                    best_c = np.where(inter[:, None], red * (1 - m) + np.array([1, .85, .8])[None] * m, best_c)
    if outline:
        best_c = np.where(edge[:, None], best_c * 0.15, best_c)
    img = (srgb(best_c).reshape(H, W, 3) * 255).astype(np.uint8)
    return Image.fromarray(img)


def label(img, text, sub=None):
    dr = ImageDraw.Draw(img)
    try:
        f = ImageFont.truetype("DejaVuSans-Bold.ttf", 17)
        fs = ImageFont.truetype("DejaVuSans.ttf", 13)
    except OSError:
        f = fs = ImageFont.load_default()
    dr.rectangle([0, 0, W, 50 if sub else 30], fill=(30, 30, 30))
    dr.text((10, 6), text, fill=(235, 235, 235), font=f)
    if sub:
        dr.text((10, 29), sub, fill=(170, 170, 170), font=fs)
    return img


def grid(imgs, cols, path):
    rows = math.ceil(len(imgs) / cols)
    g = Image.new("RGB", (cols * W + (cols - 1) * 6, rows * H + (rows - 1) * 6), (18, 18, 18))
    for i, im in enumerate(imgs):
        g.paste(im, ((i % cols) * (W + 6), (i // cols) * (H + 6)))
    g.save(path)
    print(path)


def main():
    warnings.filterwarnings('ignore', category=RuntimeWarning)
    os.makedirs(OUT, exist_ok=True)
    grey = (0.78, 0.78, 0.78)
    green = (0.29, 0.47, 0.25)
    hs = HollowSphere((0, 0, 0), 40, 25)
    eye, tgt = (120, 150, 70), (0, 0, 0)
    cutY = np.array([0, -1.0, 0, 0])  # keep y <= 0, viewer on +Y side

    a = render([(hs, grey)], eye, tgt, [cutY], [cutY], 'BACKFACES')
    b = render([(hs, grey, green)], eye, tgt, [cutY], [cutY], 'SOLID')
    c = render([(hs, grey, green)], eye, tgt, [cutY], [cutY], 'HATCH')
    sl_cap = np.array([0, 1.0, 0, 0])
    clip_all = np.array([0, 0, 0, -1.0])
    dsl = render([(hs, grey, green)], eye, tgt, [clip_all], [sl_cap], 'HATCH')
    lo = np.array([0, 1.0, 0, 4.0])    # y >= -4
    hi = np.array([0, -1.0, 0, 4.0])   # y <= 4
    e = render([(hs, grey, green)], eye, tgt, [lo, hi], [lo, hi], 'HATCH')
    grid([label(a, "Backfaces", "Plain Alt+B look: you see inside the shell"),
          label(b, "Solid cap", "Flat fill where the plane is inside material"),
          label(c, "Hatched cap", "Fill + section hatching (default)"),
          label(dsl, "Slice: section only", "Thickness 0: just the cross-section"),
          label(e, "Slice: 8 mm slab", "Thickness > 0: a slab with two caps")],
         3, os.path.join(OUT, "modes.png"))

    # multi-body
    pa = Box((-12, 0, 0), (40, 30, 30))
    pb = CylZ((14, 0, 0), 14, 50)
    pc = Box((40, 0, 0), (20, 20, 20))
    objs = [(pa, (0.30, 0.55, 0.85)), (pb, (0.90, 0.60, 0.20)), (pc, (0.45, 0.75, 0.35))]
    eye2, tgt2 = (70, -120, 140), (12, 0, 0)
    cutZ = np.array([0, 0, -1.0, 0])
    m1 = render(objs, eye2, tgt2, [cutZ], [cutZ], 'HATCH', interference=True, vary=True)
    m2 = render(objs, eye2, tgt2, [cutZ], [cutZ], 'HATCH', interference=False, vary=False)
    m3 = render(objs, eye2, tgt2, [cutZ], [cutZ], 'BACKFACES', backface_tint=(0.85, 0.2, 0.2))
    m4 = render(objs, eye2, tgt2, [cutZ], [cutZ], 'SOLID', interference=True)
    grid([label(m1, "Recommended: vary + interference", "Alternating hatch per part; overlap in red"),
          label(m4, "Alt: solid + interference", "Flat colours, overlap still flagged"),
          label(m2, "Alt: same hatch, no interference", "Last-drawn part wins; overlap hidden"),
          label(m3, "Alt: backface tint (shader trick)", "Cheap, but overlap is invisible")],
         2, os.path.join(OUT, "multibody.png"))


def bucket_figure():
    rng = np.random.default_rng(7)
    objs = []
    hues = [(0.30, 0.55, 0.85), (0.90, 0.60, 0.20), (0.45, 0.75, 0.35), (0.75, 0.45, 0.80),
            (0.85, 0.80, 0.30), (0.35, 0.75, 0.75)]
    for i in range(16):
        c = rng.uniform([-70, -70, -50], [70, 70, 50])
        if i % 3 == 0:
            objs.append((HollowSphere(c, rng.uniform(12, 20), rng.uniform(5, 9)), (0.8, 0.8, 0.8), hues[i % 6]))
        elif i % 3 == 1:
            objs.append((CylZ(c, rng.uniform(8, 14), rng.uniform(20, 50)), (0.8, 0.8, 0.8), hues[i % 6]))
        else:
            objs.append((Box(c, rng.uniform(12, 34, 3)), (0.8, 0.8, 0.8), hues[i % 6]))
    # force one interference pair near the slice
    objs.append((Box((22, -8, 6), (26, 20, 30)), (0.8, 0.8, 0.8), hues[0]))
    objs.append((CylZ((34, 0, 0), 10, 40), (0.8, 0.8, 0.8), hues[1]))
    eye, tgt = (140, -175, 150), (0, 0, 0)
    z = 6.0
    sec = render(objs, eye, tgt, [np.array([0, 0, -1.0, z])], [np.array([0, 0, -1.0, z])], 'HATCH')
    sl = render(objs, eye, tgt, [np.array([0, 0, 0, -1.0])], [np.array([0, 0, 1.0, -z])], 'HATCH')
    for im in (sec, sl):
        dr = ImageDraw.Draw(im)
        try:
            f = ImageFont.truetype("DejaVuSans.ttf", 12)
        except OSError:
            f = ImageFont.load_default()
        dr.text((12, H - 24), "Section Z  6.000 mm   step 2075 / 4750   [Hatched]", fill=(235, 235, 235), font=f)
    grid([label(sec, "Bucket scrub: section", "Range = build volume; step = one layer"),
          label(sl, "Bucket scrub: slice only", "What the printer sees at this layer")],
         2, os.path.join(OUT, "bucket.png"))


if __name__ == "__main__":
    main()
    bucket_figure()
