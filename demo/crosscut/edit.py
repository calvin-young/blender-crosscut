# SPDX-License-Identifier: GPL-3.0-or-later
"""Crosscut reel: the edit (cards, captions, cross-fades) -> out/crosscut.mp4.

    demo/crosscut/make.sh edit            # the video
    python3 demo/crosscut/edit.py --still 12.5 /tmp/x.png   # one frame at 12.5 s
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "lib"))
from compose import Caption, Edit, Frames, Still, FPS, hero_card, render, still  # noqa: E402
from PIL import Image  # noqa: E402

FR = os.path.join(ROOT, "cache", "crosscut", "frames")
OUT = os.path.join(ROOT, "out", "crosscut.mp4")
DATE = "November 2026"


def seg(name, **kw):
    return Frames(os.path.join(FR, name), **kw)


def card():
    """The first and the last frame of the video (PowerPoint shows one of them as its
    poster), so it's a section close-up rather than the end of the print."""
    im = Image.open(os.path.join(FR, "z_hero", "0000.png")).convert("RGB")
    # the viewport without Blender's top bars and status bar, 16:9
    return hero_card(im.crop((0, 100, 1692, 1052)), "Crosscut",
                     ["Section views, slices, measuring and", "print preview, live in Blender"],
                     "Calvin Young", [f"Made with Claude  ·  {DATE}"])


EDIT = Edit(
    clips=[
        Still(card, 3.0, name="title"),
        seg("a_still", hold=1.8, fade_in=0.6),
        seg("b_altb"),
        seg("c_orbit"),
        seg("d_inside"),
        seg("e_caps"),
        seg("f_planes"),
        seg("f2_any"),
        seg("f3_slab"),
        seg("g_gear"),
        seg("g2_overlaps"),
        seg("g3_measure", fade_in=0.4),
        seg("g4_overlap"),
        seg("g5_problems", fade_in=0.4),
        seg("h_bucket", fade_in=0.4),
        seg("i_slice"),
        seg("j_print", fade_in=0.5),
        seg("k_top"),
        seg("l_word", hold=1.0),
        Still(card, 3.5, fade_in=1.0, name="end"),
    ],
    captions=[
        Caption("A hollow part in Blender", "80 mm sphere, 7 mm wall", "neutral", "a_still", 0.5),
        Caption("Vanilla Blender: Alt+B clipping", "The cut is just two shells: red backfaces, no material",
                "bad", "b_altb", 0.1, "c_orbit"),
        Caption("Up close, you're inside the walls", "Hard to tell what's material and what's air",
                "bad", "d_inside", 0.2),
        Caption("Crosscut: caps on", "The same cut, now solid wherever the part is solid",
                "good", "e_caps", 1.4),
        Caption("Section planes", "X, Y or Z, scrubbed through the part", "good", "f_planes", 0.2),
        Caption("Or any angle", "The plane follows an Empty as you move and turn it", "good", "f2_any", 0.2),
        Caption("Slice", "Just the cross-section, or a slab of any thickness", "good", "f3_slab", 0.1),
        Caption("Overlaps show up", "A second part pushed into the wall", "good", "g_gear", 0.4),
        Caption("Highlight, stripes or blend", "However you want to read an overlap", "good", "g2_overlaps", 0.8),
        Caption("Measure anything you cut", "Hover for the thickness; click to pin a line or aim it", "good",
                "g3_measure", 0.4),
        Caption("Measure an overlap", "How wide it is, right at the mouse", "good", "g4_overlap", 2.6),
        Caption("It tells you when a mesh isn't sound", "Open and inside-out parts are named as the cut reaches them",
                "good", "g5_problems", 0.4, y=790),
        Caption("A packed build", "394 mechanical parts, packed by Bucket Builder", "amber", "h_bucket", 1.0),
        Caption("One slice through the build", "Every part's cross-section, moved along X", "amber", "i_slice", 0.4),
        Caption("Print Preview", "White powder, black fused layers: the build as the printer sees it",
                "amber", "j_print", 0.5),
        Caption("Layer by layer", "0.08 mm at a time, counted in the readout at the bottom", "amber", "k_top", 2.0, "k_top", 6.4),
    ],
)

if __name__ == "__main__":
    if "--still" in sys.argv:
        k = sys.argv.index("--still")
        still(EDIT, int(float(sys.argv[k + 1]) * FPS), sys.argv[k + 2])
    else:
        crf = int(os.environ.get("CRF", "20"))
        render(EDIT, OUT, crf=crf)
