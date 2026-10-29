# SPDX-License-Identifier: GPL-3.0-or-later
"""Operators."""

import bpy
import numpy as np
from bpy.props import EnumProperty, FloatProperty, IntProperty
from mathutils import Matrix, Vector

from . import engine
from .props import tag_redraw


def _s(context):
    return context.scene.crosscut


def _center_offset(context, s):
    """Offset that puts the plane through the middle of the scrub range."""
    lo, hi = engine.scrub_range(s)
    base = engine.plane_base(s)
    if base is None or hi <= lo:
        return s.offset
    return 0.5 * (lo + hi) - base


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
        s.orientation = self.axis
        if self.mode != 'KEEP':
            s.mode = self.mode
        elif was_off:
            s.mode = 'SECTION'
        if was_off or changed_axis:
            s.offset = _center_offset(context, s)
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
            s.mode = s.last_mode if s.last_mode in {'SECTION', 'SLICE'} else 'SECTION'
            if engine.plane_frame(s) is None:
                s.orientation = 'Z'
            _face_viewer(context, s)
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
