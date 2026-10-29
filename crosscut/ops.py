# SPDX-License-Identifier: GPL-3.0-or-later
"""Operators."""

import bpy
import numpy as np
from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty
from mathutils import Matrix, Vector

from . import engine
from .props import tag_redraw


def _s(context):
    return context.scene.crosscut


def _center_offset(_context, s):
    return engine.center_offset(s)


def _face_viewer(context, s):
    """Flip the plane so the side towards the viewer is the one cut away: a new
    section then shows its cut face instead of the uncut outside of the part."""
    rv3d = context.region_data
    f = engine.plane_frame(s)
    if rv3d is None or f is None or not hasattr(rv3d, "view_rotation"):
        return
    toward = np.array(rv3d.view_rotation @ Vector((0.0, 0.0, 1.0)))
    d = float(f[0] @ toward)
    if abs(d) > 0.05:  # leave it alone when looking along the plane
        s.flip = d < 0.0


def _switch_on(context, s, mode):
    """Turn Crosscut on from Off: the first time in the middle of the range,
    afterwards where it was left; cutting away the side facing the viewer."""
    if engine.plane_frame(s) is None:
        s.orientation = 'Z'
    s.mode = mode
    if not s.placed:
        s.offset = _center_offset(context, s)
        s.placed = True
    _face_viewer(context, s)
    s.last_mode = mode


class CROSSCUT_OT_set_mode(bpy.types.Operator):
    """Turn Section or Slice on, or off again when it is already on"""
    bl_idname = "crosscut.set_mode"
    bl_label = "Set Mode"
    bl_options = {'REGISTER', 'UNDO'}

    mode: EnumProperty(items=[('SECTION', "Section", ""), ('SLICE', "Slice", "")], default='SECTION')

    @classmethod
    def description(cls, _context, props):
        if props.mode == 'SLICE':
            return ("Slice: show only the cross-section, or a slab of the given thickness. "
                    "Click again to turn it off")
        return "Section: cut the view with a plane and keep one side. Click again to turn it off"

    def execute(self, context):
        s = _s(context)
        if s.mode == self.mode:
            s.last_mode = s.mode
            s.mode = 'OFF'
        elif s.mode == 'OFF':
            _switch_on(context, s, self.mode)
        else:
            s.mode = self.mode
            s.last_mode = self.mode
        tag_redraw()
        return {'FINISHED'}


class CROSSCUT_OT_from_view(bpy.types.Operator):
    """Put the plane parallel to the view, through the middle of the targets. It stays put when
    you orbit; click again to face the current view"""
    bl_idname = "crosscut.from_view"
    bl_label = "Plane from View"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.region_data is not None

    def execute(self, context):
        s = _s(context)
        rv3d = context.region_data
        # view-local +Z points at the viewer; Section keeps the side opposite
        # the normal, so the half nearest the viewer is the one cut away
        n = np.array(rv3d.view_rotation @ Vector((0.0, 0.0, 1.0)))
        n = n / np.linalg.norm(n)
        pts = engine.target_points(context, s)
        if len(pts):
            lo, hi = float((pts @ n).min()), float((pts @ n).max())
            base = 0.5 * (lo + hi)
        else:
            base = float(n @ np.array(context.scene.cursor.location))
        s.view_normal = n
        s.view_base = base
        s.orientation = 'VIEW'
        s.offset = 0.0
        s.flip = False
        s.placed = True
        if s.mode == 'OFF':
            s.mode = s.last_mode if s.last_mode in {'SECTION', 'SLICE'} else 'SECTION'
            s.last_mode = s.mode
        tag_redraw()
        return {'FINISHED'}


def _zero_slice(s):
    return s.mode == 'SLICE' and s.thickness <= 1e-9


class CROSSCUT_OT_select_section(bpy.types.Operator):
    """Click-select parts by their section in a zero-thickness slice (Blender
    can't select them there: everything else is clipped away)"""
    bl_idname = "crosscut.select_section"
    bl_label = "Select by Section"
    bl_options = {'REGISTER', 'UNDO'}

    extend: BoolProperty(name="Extend", description="Toggle the part's selection instead of replacing it")

    @classmethod
    def poll(cls, context):
        sc = context.scene
        return (sc is not None and _zero_slice(sc.crosscut) and context.mode == 'OBJECT'
                and context.region_data is not None)

    def invoke(self, context, event):
        from bpy_extras import view3d_utils
        s = _s(context)
        planes = engine.compute_planes(s)
        if not planes:
            return {'PASS_THROUGH'}
        plane = np.asarray(planes[1][0][0], dtype=np.float64)
        xy = (event.mouse_region_x, event.mouse_region_y)
        o = np.array(view3d_utils.region_2d_to_origin_3d(context.region, context.region_data, xy))
        d = np.array(view3d_utils.region_2d_to_vector_3d(context.region, context.region_data, xy))
        denom = float(plane[:3] @ d)
        if abs(denom) < 1e-12:
            return {'PASS_THROUGH'}
        p = o + d * (-(float(plane[:3] @ o) + float(plane[3])) / denom)
        hits = engine.objects_at(context, s, p, plane, context.evaluated_depsgraph_get())
        if not hits:
            return {'PASS_THROUGH'}  # Blender's own click-select deselects as usual
        active = context.view_layer.objects.active
        # clicking again where parts overlap cycles through them
        ob = hits[(hits.index(active) + 1) % len(hits)] if active in hits and len(hits) > 1 else hits[0]
        if self.extend:
            if ob.select_get() and ob == active:
                ob.select_set(False)
                return {'FINISHED'}
        else:
            for o2 in context.selected_objects:
                o2.select_set(False)
        ob.select_set(True)
        context.view_layer.objects.active = ob
        return {'FINISHED'}


class CROSSCUT_OT_section(bpy.types.Operator):
    """Section the view along an axis (Section mode keeps one side; Slice keeps a slice)"""
    bl_idname = "crosscut.section"
    bl_label = "Section"
    bl_options = {'REGISTER', 'UNDO'}

    axis: EnumProperty(items=[('X', "X", ""), ('Y', "Y", ""), ('Z', "Z", ""), ('OBJECT', "Object", "")],
                       default='Z')
    mode: EnumProperty(items=[('KEEP', "Keep", "Keep the current mode (Section if off)"),
                              ('SECTION', "Section", ""), ('SLICE', "Slice", "")], default='KEEP')

    @classmethod
    def description(cls, _context, props):
        return f"Section the view with a plane normal to {props.axis}"

    def execute(self, context):
        s = _s(context)
        was_off = s.mode == 'OFF'
        changed_axis = s.orientation != self.axis
        s.orientation = self.axis  # re-centres when the axis changes
        mode = self.mode if self.mode != 'KEEP' else (s.mode if not was_off else 'SECTION')
        if was_off:
            s.placed = True  # centred just now or by the axis change below
            s.offset = _center_offset(context, s)
            _switch_on(context, s, mode)
        else:
            s.mode = mode
            if changed_axis:
                _face_viewer(context, s)
        s.last_mode = s.mode
        tag_redraw()
        return {'FINISHED'}


class CROSSCUT_OT_toggle(bpy.types.Operator):
    """Turn Crosscut on (last used mode) or off"""
    bl_idname = "crosscut.toggle"
    bl_label = "Toggle Crosscut"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        s = _s(context)
        if s.mode == 'OFF':
            _switch_on(context, s, s.last_mode if s.last_mode in {'SECTION', 'SLICE'} else 'SECTION')
        else:
            s.last_mode = s.mode
            s.mode = 'OFF'
        tag_redraw()
        return {'FINISHED'}


class CROSSCUT_OT_toggle_slice(bpy.types.Operator):
    """Switch between Section (keep one side) and Slice (show only the cross-section)"""
    bl_idname = "crosscut.toggle_slice"
    bl_label = "Section / Slice"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        s = _s(context)
        s.mode = 'SECTION' if s.mode == 'SLICE' else 'SLICE'
        s.last_mode = s.mode
        tag_redraw()
        return {'FINISHED'}


class CROSSCUT_OT_toggle_caps(bpy.types.Operator):
    """Switch between seeing backfaces (native clipping look) and solid caps"""
    bl_idname = "crosscut.toggle_caps"
    bl_label = "Toggle Caps"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        s = _s(context)
        if s.cap_style == 'BACKFACES':
            s.cap_style = s.last_cap_style if s.last_cap_style in {'SOLID', 'HATCH'} else 'HATCH'
        else:
            s.last_cap_style = s.cap_style
            s.cap_style = 'BACKFACES'
        tag_redraw()
        return {'FINISHED'}


class CROSSCUT_OT_flip(bpy.types.Operator):
    """Keep the other side of the section plane"""
    bl_idname = "crosscut.flip"
    bl_label = "Flip Side"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        s = _s(context)
        s.flip = not s.flip
        tag_redraw()
        return {'FINISHED'}


class CROSSCUT_OT_step(bpy.types.Operator):
    """Move the plane by the step distance"""
    bl_idname = "crosscut.step"
    bl_label = "Step Plane"
    bl_options = {'REGISTER'}  # no undo push per wheel tick

    direction: IntProperty(default=1)
    multiplier: FloatProperty(default=1.0, min=0.0)

    @classmethod
    def poll(cls, context):
        return context.scene is not None and context.scene.crosscut.mode != 'OFF'

    def execute(self, context):
        s = _s(context)
        s.offset += s.step * self.multiplier * (1 if self.direction >= 0 else -1)
        tag_redraw()
        return {'FINISHED'}


class CROSSCUT_OT_center(bpy.types.Operator):
    """Move the plane to the middle of the scrub range"""
    bl_idname = "crosscut.center"
    bl_label = "Center"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        s = _s(context)
        s.offset = _center_offset(context, s)
        tag_redraw()
        return {'FINISHED'}


class CROSSCUT_OT_to_cursor(bpy.types.Operator):
    """Move the plane through the 3D cursor"""
    bl_idname = "crosscut.to_cursor"
    bl_label = "To Cursor"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        s = _s(context)
        f = engine.plane_frame(s)
        if f is None:
            return {'CANCELLED'}
        n, base = f
        s.offset = float(n @ np.array(context.scene.cursor.location)) - base
        tag_redraw()
        return {'FINISHED'}


def _selection_point(context):
    ob = context.active_object
    if context.mode == 'EDIT_MESH' and ob is not None and ob.type == 'MESH':
        ob.update_from_editmode()
        me = ob.data
        sel = np.zeros(len(me.vertices), dtype=bool)
        me.vertices.foreach_get("select", sel)
        if sel.any():
            co = np.empty(len(me.vertices) * 3)
            me.vertices.foreach_get("co", co)
            p = co.reshape(-1, 3)[sel].mean(0)
            m = np.array(ob.matrix_world)
            return m[:3, :3] @ p + m[:3, 3]
    obs = context.selected_objects or ([ob] if ob else [])
    if not obs:
        return None
    pts = np.concatenate([engine._corners(o) for o in obs])
    return 0.5 * (pts.min(0) + pts.max(0))


class CROSSCUT_OT_to_selection(bpy.types.Operator):
    """Move the plane through the selection (selected vertices in Edit Mode, else the
    centre of the selected objects' bounds)"""
    bl_idname = "crosscut.to_selection"
    bl_label = "To Selection"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        s = _s(context)
        f = engine.plane_frame(s)
        p = _selection_point(context)
        if f is None or p is None:
            self.report({'WARNING'}, "Nothing selected")
            return {'CANCELLED'}
        n, base = f
        s.offset = float(n @ p) - base
        tag_redraw()
        return {'FINISHED'}


class CROSSCUT_OT_add_plane(bpy.types.Operator):
    """Add an Empty to use as a freely placed section plane (its local Z is the normal)"""
    bl_idname = "crosscut.add_plane"
    bl_label = "Add Plane Object"
    bl_options = {'REGISTER', 'UNDO'}

    align: EnumProperty(
        items=[('VIEW', "View", "Face the current view"),
               ('CURRENT', "Current", "Match the current section plane")],
        default='VIEW',
    )

    def execute(self, context):
        s = _s(context)
        rv3d = context.region_data
        loc = context.scene.cursor.location.copy()
        if self.align == 'VIEW' and rv3d is not None:
            # view-local +Z points at the viewer; Section keeps the side opposite
            # the normal, so the half nearest the viewer is the one cut away
            rot = rv3d.view_rotation.to_matrix()
        else:
            f = engine.plane_frame(s)
            n = Vector(f[0]) if f else Vector((0, 0, 1))
            if f:
                loc = loc - n * (n.dot(loc) - (f[1] + s.offset))
            rot = n.to_track_quat('Z', 'Y').to_matrix()
        ob = s.plane_object
        if ob is None:
            ob = bpy.data.objects.new("Crosscut Plane", None)
            ob.empty_display_type = 'SINGLE_ARROW'
            pts = engine.target_points(context, s)
            size = float(np.linalg.norm(pts.max(0) - pts.min(0))) * 0.3 if len(pts) else 1.0
            ob.empty_display_size = max(size, 1e-3)
            context.scene.collection.objects.link(ob)
        ob.matrix_world = Matrix.Translation(loc) @ rot.to_4x4()
        s.plane_object = ob
        s.orientation = 'OBJECT'
        s.offset = 0.0
        if s.mode == 'OFF':
            s.mode = 'SECTION'
        tag_redraw()
        return {'FINISHED'}


class CROSSCUT_OT_use_bounds(bpy.types.Operator):
    """Use the active object's bounds as the scrub range (e.g. a build volume)"""
    bl_idname = "crosscut.use_bounds"
    bl_label = "Use Active as Range"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.active_object is not None

    def execute(self, context):
        s = _s(context)
        s.range_source = 'OBJECT'
        s.range_object = context.active_object
        tag_redraw()
        return {'FINISHED'}


classes = (
    CROSSCUT_OT_set_mode,
    CROSSCUT_OT_from_view,
    CROSSCUT_OT_select_section,
    CROSSCUT_OT_section,
    CROSSCUT_OT_toggle,
    CROSSCUT_OT_toggle_slice,
    CROSSCUT_OT_toggle_caps,
    CROSSCUT_OT_flip,
    CROSSCUT_OT_step,
    CROSSCUT_OT_center,
    CROSSCUT_OT_to_cursor,
    CROSSCUT_OT_to_selection,
    CROSSCUT_OT_add_plane,
    CROSSCUT_OT_use_bounds,
)


def register():
    for c in classes:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
