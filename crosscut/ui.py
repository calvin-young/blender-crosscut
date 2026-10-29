# SPDX-License-Identifier: GPL-3.0-or-later
"""Panels, pie menu, header button and keymaps."""

import bpy

from . import draw, engine

_keymaps = []


def _draw_main(layout, context, compact=False):
    s = context.scene.crosscut
    col = layout.column()
    row = col.row(align=True)
    row.prop(s, "mode", expand=True)

    col.separator()
    row = col.row(align=True)
    row.prop(s, "orientation", expand=True)
    sub = row.row(align=True)
    sub.enabled = s.mode == 'SECTION'
    sub.operator("crosscut.flip", text="", icon='ARROW_LEFTRIGHT', depress=s.flip)
    if s.orientation == 'OBJECT':
        r = col.row(align=True)
        r.prop(s, "plane_object", text="")
        op = r.operator("crosscut.add_plane", text="", icon='ADD')
        op.align = 'VIEW'

    active = s.mode != 'OFF'
    box = col.column(align=True)
    box.enabled = active
    box.prop(s, "position", slider=True)
    r = box.row(align=True)
    r.prop(s, "offset", text="")
    st = r.operator("crosscut.step", text="", icon='TRIA_LEFT')
    st.direction = -1
    st = r.operator("crosscut.step", text="", icon='TRIA_RIGHT')
    st.direction = 1
    box.prop(s, "step")
    if s.mode == 'SLICE':
        box.prop(s, "thickness")
    if not compact:
        r = box.row(align=True)
        r.operator("crosscut.center", text="Center")
        r.operator("crosscut.to_cursor", text="Cursor")
        r.operator("crosscut.to_selection", text="Selection")

    col.separator()
    row = col.row(align=True)
    row.prop(s, "cap_style", expand=True)


class CROSSCUT_PT_main(bpy.types.Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Crosscut"
    bl_label = "Crosscut"

    def draw(self, context):
        _draw_main(self.layout, context)
        info = draw.last_info(_window_region(context))
        if info:
            col = self.layout.column(align=True)
            if info.get("error"):
                col.label(text="Draw error (see console)", icon='ERROR')
            for name in info.get("open", [])[:5]:
                col.label(text=f"Open section: {name}", icon='ERROR')


def _window_region(context):
    area = context.area
    if area is None:
        return None
    for r in area.regions:
        if r.type == 'WINDOW':
            return r
    return None


class CROSSCUT_PT_display(bpy.types.Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Crosscut"
    bl_label = "Caps"
    bl_parent_id = "CROSSCUT_PT_main"

    def draw(self, context):
        s = context.scene.crosscut
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        col = layout.column()
        col.active = s.cap_style != 'BACKFACES'
        col.prop(s, "color_source")
        if s.color_source in {'SINGLE', 'AUTO'}:
            col.prop(s, "single_color")
        sub = col.column()
        sub.active = s.cap_style == 'HATCH'
        sub.prop(s, "hatch_space")
        if s.hatch_space == 'SCREEN':
            sub.prop(s, "hatch_pitch_px", text="Spacing (px)")
        else:
            sub.prop(s, "hatch_pitch")
        sub.prop(s, "hatch_angle")
        sub.prop(s, "hatch_width")
        sub.prop(s, "hatch_vary")
        r = col.row(heading="Outline")
        r.prop(s, "outline", text="")
        sr = r.row()
        sr.active = s.outline
        sr.prop(s, "outline_width", text="")
        col.prop(s, "interference")
        layout.separator()
        col = layout.column(heading="Show")
        col.prop(s, "show_frame")
        col.prop(s, "show_readout")
        col = layout.column(heading="Alt+B")
        col.prop(s, "cap_native", text="Cap Alt+B Clipping")


class CROSSCUT_PT_targets(bpy.types.Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Crosscut"
    bl_label = "Targets & Range"
    bl_parent_id = "CROSSCUT_PT_main"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        s = context.scene.crosscut
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        col = layout.column()
        col.prop(s, "targets")
        if s.targets == 'COLLECTION':
            col.prop(s, "target_collection")
        col.separator()
        col.prop(s, "range_source")
        if s.range_source == 'OBJECT':
            r = col.row(align=True)
            r.prop(s, "range_object", text="Object")
            r.operator("crosscut.use_bounds", text="", icon='EYEDROPPER')
        lo, hi = engine.scrub_range(s)
        col.label(text=f"Range {draw.fmt_length(context.scene, lo)} → {draw.fmt_length(context.scene, hi)}")
        layout.label(text="Wire/Bounds-display objects are never capped", icon='INFO')


class CROSSCUT_PT_popover(bpy.types.Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'HEADER'
    bl_label = "Crosscut"
    bl_ui_units_x = 12

    def draw(self, context):
        _draw_main(self.layout, context, compact=True)


class CROSSCUT_MT_pie(bpy.types.Menu):
    bl_label = "Crosscut"
    bl_idname = "CROSSCUT_MT_pie"

    def draw(self, context):
        s = context.scene.crosscut
        pie = self.layout.menu_pie()
        # order: W, E, S, N, NW, NE, SW, SE
        pie.operator("crosscut.section", text="Section X").axis = 'X'
        pie.operator("crosscut.section", text="Section Y").axis = 'Y'
        pie.operator("crosscut.toggle", text="Off" if s.mode != 'OFF' else "On",
                     icon='HIDE_ON' if s.mode != 'OFF' else 'HIDE_OFF')
        pie.operator("crosscut.section", text="Section Z").axis = 'Z'
        pie.operator("crosscut.toggle_caps",
                     text="Show Backfaces" if s.cap_style != 'BACKFACES' else "Show Caps",
                     icon='MOD_SOLIDIFY')
        pie.operator("crosscut.toggle_slice",
                     text="Slice" if s.mode != 'SLICE' else "Section", icon='ALIGN_JUSTIFY')
        pie.operator("crosscut.flip", icon='ARROW_LEFTRIGHT')
        pie.operator("crosscut.add_plane", text="Plane from View", icon='VIEW_CAMERA').align = 'VIEW'


def _header_button(self, context):
    if context.scene is None or not hasattr(context.scene, "crosscut"):
        return
    s = context.scene.crosscut
    row = self.layout.row(align=True)
    row.operator("crosscut.toggle", text="", icon='MOD_BOOLEAN', depress=s.mode != 'OFF')
    row.popover(panel="CROSSCUT_PT_popover", text="")


classes = (
    CROSSCUT_PT_main,
    CROSSCUT_PT_display,
    CROSSCUT_PT_targets,
    CROSSCUT_PT_popover,
    CROSSCUT_MT_pie,
)


def _add_keymaps():
    kc = bpy.context.window_manager.keyconfigs.addon
    if kc is None:
        return
    km = kc.keymaps.new(name="3D View", space_type='VIEW_3D')
    kmi = km.keymap_items.new("wm.call_menu_pie", 'B', 'PRESS', shift=True, alt=True)
    kmi.properties.name = "CROSSCUT_MT_pie"
    _keymaps.append((km, kmi))
    for event, direction in (('WHEELUPMOUSE', 1), ('WHEELDOWNMOUSE', -1)):
        kmi = km.keymap_items.new("crosscut.step", event, 'PRESS', shift=True, alt=True)
        kmi.properties.direction = direction
        _keymaps.append((km, kmi))
        kmi = km.keymap_items.new("crosscut.step", event, 'PRESS', shift=True, alt=True, ctrl=True)
        kmi.properties.direction = direction
        kmi.properties.multiplier = 10.0
        _keymaps.append((km, kmi))


def register():
    for c in classes:
        bpy.utils.register_class(c)
    bpy.types.VIEW3D_HT_header.append(_header_button)
    _add_keymaps()


def unregister():
    for km, kmi in _keymaps:
        try:
            km.keymap_items.remove(kmi)
        except (ReferenceError, RuntimeError):
            pass
    _keymaps.clear()
    bpy.types.VIEW3D_HT_header.remove(_header_button)
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
