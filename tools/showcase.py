# SPDX-License-Identifier: GPL-3.0-or-later
"""Build a demo scene and capture viewport screenshots of every Crosscut mode.

Usage (Crosscut must be installed and enabled):
    Blender > Scripting workspace > Text > Open > tools/showcase.py > Run Script
or from a terminal:
    blender --python tools/showcase.py

It adds a new scene called "Crosscut Showcase" (your current scene is left
alone and nothing is saved) and writes PNGs to ~/crosscut_showcase/.
Switch back to the Layout workspace first if you run it from the Text Editor,
so there is a 3D viewport on screen to capture.
"""

import math
import os

import bmesh
import bpy
from mathutils import Euler, Vector

OUT = os.path.join(os.path.expanduser("~"), "crosscut_showcase")


# -------------------------------------------------------------- demo geometry

def hollow_sphere(name, r_out, r_in, loc, color):
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=64, v_segments=32, radius=r_out)
    inner = bmesh.new()
    bmesh.ops.create_uvsphere(inner, u_segments=64, v_segments=32, radius=r_in)
    bmesh.ops.reverse_faces(inner, faces=inner.faces[:])
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    tmp = bpy.data.meshes.new(name + "_in")
    inner.to_mesh(tmp)
    bm.free()
    inner.free()
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.from_mesh(tmp)
    bm.to_mesh(me)
    bm.free()
    bpy.data.meshes.remove(tmp)
    for p in me.polygons:
        p.use_smooth = True
    return _link(name, me, loc, color)


def box(name, size, loc, color, open_side=False):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=Vector(size), verts=bm.verts)
    if open_side:
        top = max(bm.faces, key=lambda f: f.calc_center_median().y)
        bmesh.ops.delete(bm, geom=[top], context='FACES_ONLY')
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    return _link(name, me, loc, color)


def cylinder(name, radius, depth, loc, color, rot=(0, 0, 0)):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=64, radius1=radius, radius2=radius, depth=depth)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = _link(name, me, loc, color)
    ob.rotation_euler = Euler(rot)
    return ob


def _link(name, me, loc, color):
    ob = bpy.data.objects.new(name, me)
    ob.location = loc
    ob.color = (*color, 1.0)
    bpy.context.scene.collection.objects.link(ob)
    return ob


# ----------------------------------------------------------------- capture

def view3d():
    best = None
    for area in bpy.context.window.screen.areas:
        if area.type == 'VIEW_3D':
            if best is None or area.width * area.height > best.width * best.height:
                best = area
    if best is None:
        raise RuntimeError("No 3D viewport on screen: switch to the Layout workspace and run again")
    region = next(r for r in best.regions if r.type == 'WINDOW')
    return best, region


def look(area, target, distance, rot_deg, ortho=False):
    rv3d = area.spaces.active.region_3d
    rv3d.view_location = Vector(target)
    rv3d.view_distance = distance
    rv3d.view_rotation = Euler([math.radians(a) for a in rot_deg]).to_quaternion()
    rv3d.view_perspective = 'ORTHO' if ortho else 'PERSP'


def shoot(area, region, name):
    for _ in range(3):  # first draw syncs the clip planes, then they apply
        bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)
    path = os.path.join(OUT, name + ".png")
    with bpy.context.temp_override(area=area, region=region):
        bpy.ops.screen.screenshot_area(filepath=path)
    print("Crosscut showcase:", path)


def configure(s, **kw):
    defaults = dict(mode='OFF', orientation='Y', offset=0.0, flip=False, thickness=0.0,
                    cap_style='HATCH', targets='VISIBLE', color_source='AUTO', hatch_vary=True,
                    interference=True, outline=True, show_frame=False, show_readout=True)
    defaults.update(kw)
    for k, v in defaults.items():
        setattr(s, k, v)


def main():
    if not hasattr(bpy.types.Scene, "crosscut"):
        raise RuntimeError("Enable the Crosscut add-on first")
    os.makedirs(OUT, exist_ok=True)

    scene = bpy.data.scenes.new("Crosscut Showcase")
    bpy.context.window.scene = scene
    scene.unit_settings.system = 'METRIC'
    scene.unit_settings.scale_length = 0.001
    scene.unit_settings.length_unit = 'MILLIMETERS'

    sphere = hollow_sphere("hollow-sphere", 40.0, 25.0, (0, 0, 0), (0.80, 0.80, 0.80))

    area, region = view3d()
    space = area.spaces.active
    space.shading.type = 'SOLID'
    space.shading.color_type = 'OBJECT'
    space.overlay.show_floor = True
    space.clip_end = 10000.0
    s = scene.crosscut

    # 1-3: the same half section with each cap style
    look(area, (0, 0, 0), 190, (70, 0, 35))
    for style, label in (('BACKFACES', "01_section_backfaces"),
                         ('SOLID', "02_section_solid"),
                         ('HATCH', "03_section_hatched")):
        configure(s, mode='SECTION', orientation='Y', cap_style=style)
        shoot(area, region, label)

    # 4-5: slices
    configure(s, mode='SLICE', orientation='Y', offset=0.0, thickness=0.0)
    shoot(area, region, "04_slice_section_only")
    configure(s, mode='SLICE', orientation='Y', offset=10.0, thickness=4.0)
    shoot(area, region, "05_slice_slab_4mm")

    # 6: overlapping bodies -> per-object hatching + interference
    sphere.hide_set(True)
    a = box("part-a", (40, 30, 30), (-12, 0, 0), (0.30, 0.55, 0.85))
    b = cylinder("part-b", 14, 50, (14, 0, 0), (0.90, 0.60, 0.20), rot=(0, 0, 0))
    c = box("part-c", (20, 20, 20), (40, 0, 0), (0.45, 0.75, 0.35))
    look(area, (12, 0, 0), 190, (60, 0, 20))
    configure(s, mode='SECTION', orientation='Z', offset=0.0)
    shoot(area, region, "06_multibody_interference")
    configure(s, mode='SECTION', orientation='Z', offset=0.0, hatch_vary=False, interference=False)
    shoot(area, region, "07_multibody_no_interference")

    # 8: open (non-manifold) mesh is flagged
    for ob in (a, b, c):
        ob.hide_set(True)
    box("open-box", (30, 30, 30), (0, 0, 0), (0.7, 0.5, 0.8), open_side=True)
    look(area, (0, 0, 0), 130, (60, 0, 30))
    configure(s, mode='SECTION', orientation='Z', offset=0.0)
    shoot(area, region, "08_open_mesh_warning")

    # 9: Blender's own Alt+B box gets caps too
    for ob in scene.objects:
        ob.hide_set(ob.name != "hollow-sphere")
    configure(s, mode='OFF', cap_native=True, cap_style='HATCH')
    look(area, (0, 0, 0), 190, (70, 0, 35))
    with bpy.context.temp_override(area=area, region=region):
        w, h = region.width, region.height
        bpy.ops.view3d.clip_border(xmin=int(w * 0.25), xmax=int(w * 0.75), ymin=int(h * 0.05),
                                   ymax=int(h * 0.55), wait_for_input=False)
    shoot(area, region, "09_native_altb_capped")
    space.region_3d.use_clip_planes = False

    # 10: plane frame + readout with a build-volume range object
    for ob in scene.objects:
        ob.hide_set(ob.name not in {"hollow-sphere"})
    vol = box("build-volume", (120, 120, 120), (0, 0, 0), (0.5, 0.5, 0.5))
    vol.display_type = 'WIRE'
    configure(s, mode='SECTION', orientation='Z', offset=12.0, show_frame=True,
              range_source='OBJECT', range_object=vol, step=0.08)
    look(area, (0, 0, 0), 300, (60, 0, 30))
    shoot(area, region, "10_range_object_readout")

    configure(s, mode='OFF')
    print("Crosscut showcase: done ->", OUT)


if __name__ == "__main__":
    main()
