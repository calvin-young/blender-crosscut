# SPDX-License-Identifier: GPL-3.0-or-later
"""Panels, pie menu, header button and keymaps."""

import bpy

from . import draw, engine

_keymaps = []


def _draw_main(layout, context):
    s = context.scene.crosscut
    col = layout.column()
    # Clip / Section / Slice: one or none (Clip is Blender's own clipping region)
    row = col.row(align=True)
    rv3d = getattr(context.space_data, "region_3d", None)
    row.operator("crosscut.clip", text="Clip", icon='SHADING_BBOX',
                 depress=s.mode == 'OFF' and rv3d is not None and rv3d.use_clip_planes)
    row.operator("crosscut.set_mode", text="Section", icon='MOD_BOOLEAN',
                 depress=s.mode == 'SECTION').mode = 'SECTION'
    row.operator("crosscut.set_mode", text="Slice", icon='ALIGN_JUSTIFY',
                 depress=s.mode == 'SLICE').mode = 'SLICE'
    # applies to Clip, Section and Slice alike; Backfaces = no caps anywhere
    row = col.row(align=True)
    row.prop(s, "cap_style", expand=True)

    col.separator()
    row = col.row(align=True)
    for key, label in (('X', "X"), ('Y', "Y"), ('Z', "Z"), ('OBJECT', "Object")):
        # from off these start a plane; a lit one turns it off again, as Section and Slice do
        op = row.operator("crosscut.section", text=label, depress=s.orientation == key)
        op.axis = key
        op.mode = 'LAST'
    row.operator("crosscut.from_view", text="View", depress=s.orientation == 'VIEW').toggle = True
    sub = row.row(align=True)
    sub.enabled = s.mode == 'SECTION'
    sub.operator("crosscut.flip", text="", icon='ARROW_LEFTRIGHT', depress=s.flip)
    if s.orientation == 'OBJECT':
        r = col.row(align=True)
        r.prop(s, "plane_object", text="")
        op = r.operator("crosscut.add_plane", text="", icon='ADD')
        op.align = 'VIEW'
        r = col.row(align=True)
        r.prop(s, "object_axis", expand=True)

    clipping = s.mode == 'OFF' and rv3d is not None and rv3d.use_clip_planes
    if clipping:
        box = col.column(align=True)
        for i, (axis, _centre, _half) in enumerate(engine.clip_axes(rv3d)[:2]):
            r = box.row(align=True)
            label = f"Scrub {engine.clip_axis_label(axis)}"
            if s.scrub_distance:
                r.prop(s, f"clip_position_{i + 1}", text=label)
            else:
                r.prop(s, f"clip_scrub_{i + 1}", text=label, slider=True)
            for icon, direction in (('TRIA_LEFT', -1), ('TRIA_RIGHT', 1)):
                st = r.operator("crosscut.step", text="", icon=icon)
                st.direction = direction
                st.clip_axis = i
    elif s.mode != 'OFF':  # hide, don't grey out, what doesn't apply (Flip above is the exception)
        r = col.row(align=True)
        if s.scrub_distance:
            r.prop(s, "offset")
        else:
            r.prop(s, "position", slider=True)
        st = r.operator("crosscut.step", text="", icon='TRIA_LEFT')
        st.direction = -1
        r.operator("crosscut.to_cursor", text="", icon='PIVOT_CURSOR')
        r.operator("crosscut.center", text="", icon='SNAP_MIDPOINT')
        r.operator("crosscut.to_selection", text="", icon='RESTRICT_SELECT_OFF')
        st = r.operator("crosscut.step", text="", icon='TRIA_RIGHT')
        st.direction = 1
    if clipping or s.mode != 'OFF':
        col.separator()
        r = col.row(align=True)
        r.operator("crosscut.measure", text="Measure", icon='DRIVER_DISTANCE', depress=draw.measure_running())
        sub = r.row(align=True)
        sub.enabled = draw.measure_has_lines()  # greyed, not hidden, so the row doesn't jump
        sub.operator("crosscut.measure_clear", text="", icon='X')
        r.prop(s, "measure_keep", text="", icon='PINNED' if s.measure_keep else 'UNPINNED', toggle=True)


def _window_region(context):
    area = context.area
    if area is None:
        return None
    for r in area.regions:
        if r.type == 'WINDOW':
            return r
    return None


def _split(layout):
    layout.use_property_split = True
    layout.use_property_decorate = False
    return layout.column()


def _rule(col):
    try:
        col.separator(factor=1.5, type='LINE')
    except TypeError:  # older Blender
        col.separator()


def _draw_cut_faces(layout, context):
    s = context.scene.crosscut
    col = _split(layout)
    if s.cap_style == 'BACKFACES':
        col.label(text="Backfaces: cut faces aren't filled", icon='INFO')
        if s.mode == 'SLICE':
            _outline_row(col, s)  # a zero-thickness slice still shows its outline
        return
    # which parts
    col.prop(s, "targets")
    if s.targets == 'COLLECTION':
        col.prop(s, "target_collection")
    names = engine.hidden_from_caps(context, s)
    if names:
        more = f" (+{len(names) - 2})" if len(names) > 2 else ""
        col.label(text="Not filled (Wire/Bounds display): " + ", ".join(names[:2]) + more, icon='INFO')
    _rule(col)
    # their color
    col.prop(s, "color_source")
    if s.color_source == 'SINGLE' or (s.color_source == 'AUTO' and draw.auto_uses_cap_color(context, s)):
        col.prop(s, "single_color")
    if s.color_source != 'SINGLE':
        col.prop(s, "fill_saturation", slider=True)
        col.prop(s, "fill_brightness", slider=True)
        col.prop(s, "fill_tint")
        col.prop(s, "fill_tint_amount", slider=True)
    col.prop(s, "fill_opacity", slider=True)
    col.prop(s, "open_opacity", slider=True)
    _rule(col)
    # the lines on them
    if s.cap_style == 'HATCH':
        col.prop(s, "hatch_space")
        if s.hatch_space == 'SCREEN':
            col.prop(s, "hatch_pitch_px", text="Spacing (px)")
        else:
            col.prop(s, "hatch_pitch")
            col.prop(s, "hatch_scale", slider=True)
        col.prop(s, "hatch_angle")
        col.prop(s, "hatch_width")
        col.prop(s, "hatch_vary")
    _outline_row(col, s)
    _rule(col)
    # where they overlap
    col.prop(s, "overlap_style", expand=True)
    if s.overlap_style == 'STRIPES':
        if s.cap_style != 'HATCH':
            col.prop(s, "hatch_space", text="Stripe Space")
        if s.hatch_space == 'SCREEN':
            col.prop(s, "stripe_width_px", text="Stripe Width (px)")
        else:
            col.prop(s, "stripe_width")
    elif s.overlap_style == 'HIGHLIGHT':
        col.prop(s, "interference_style")
        col.prop(s, "interference_color")
        if s.interference_style != 'SOLID':
            col.prop(s, "interference_line_color")
        col.prop(s, "interference_opacity", slider=True)


def _outline_row(col, s):
    r = col.row(heading="Outline")
    r.prop(s, "outline", text="")
    if s.outline:
        r.prop(s, "outline_width", text="")


def _draw_plane(layout, context):
    s = context.scene.crosscut
    col = _split(layout)
    col.prop(s, "thickness")
    col.prop(s, "range_source")
    if s.range_source == 'OBJECT':
        r = col.row(align=True)
        r.prop(s, "range_object", text="Object")
        r.operator("crosscut.use_bounds", text="", icon='EYEDROPPER')
    lo, hi = engine.scrub_range(s)
    # a label in the property-split columns, lined up with the rows above
    sp = col.split(factor=0.4)
    r = sp.row()
    r.alignment = 'RIGHT'
    r.label(text="Range")
    sp.label(text=f"{draw.fmt_length(context.scene, lo)} → {draw.fmt_length(context.scene, hi)}")
    col.prop(s, "scrub_distance")
    col.prop(s, "step")
    col.separator()
    col.prop(s, "plane_display", text="Display")
    if s.plane_display != 'NONE':
        col.prop(s, "plane_color")
        if s.mode == 'SLICE':
            col.prop(s, "plane_color_2")
        if s.plane_display in {'TINT', 'HATCH'}:
            col.prop(s, "plane_opacity", slider=True)


def _draw_measure(layout, context):
    s = context.scene.crosscut
    col = _split(layout)
    for heading, on, color in (("Local Width", "measure_local", "measure_color"),
                               ("Overlap Max", "measure_max", "measure_max_color"),
                               ("Section Max", "measure_section_max", "measure_max_color")):
        r = col.row(heading=heading)
        r.prop(s, on, text="")
        sub = r.row()
        sub.active = getattr(s, on)
        sub.prop(s, color, text="")
    col.prop(s, "measure_ignore_overlaps")
    if s.hatch_space == 'SCREEN':
        col.prop(s, "measure_text_size", text="Text Size (px)")
    else:
        col.prop(s, "measure_text_height")


def _draw_print_preview(layout, context):
    s = context.scene.crosscut
    col = _split(layout)
    col.active = s.print_preview
    if s.mode == 'OFF':
        col.label(text="Needs Section or Slice", icon='INFO')
    col.prop(s, "powder_color")
    col.prop(s, "fused_color")
    col.prop(s, "powder_grain", slider=True)
    if not (s.range_source == 'OBJECT' and s.range_object is not None):
        col.prop(s, "bed_margin")


def _draw_settings(layout, context):
    """Every option beyond the main controls. Layout panels rather than sub-panels:
    they sit closer to the controls above, and their open state can be set."""
    s = context.scene.crosscut
    header, body = layout.panel_prop(s, "ui_settings")
    header.label(text="Settings")
    if body is None:
        return
    col = body.column()
    col.prop(s, "show_readout")
    overlay = getattr(context.space_data, "overlay", None)
    if overlay is not None:
        col.prop(overlay, "show_face_orientation", text="Face Orientation")
    col.prop(s, "clip_tint")
    for prop, label, fn in (("ui_cut_faces", "Cut Faces", _draw_cut_faces),
                            ("ui_plane", "Section/Slice Plane", _draw_plane),
                            ("ui_measure", "Measure", _draw_measure)):
        header, sub = body.panel_prop(s, prop)
        header.label(text=label)
        if sub is not None:
            fn(sub, context)
    header, sub = body.panel_prop(s, "ui_print_preview")
    header.prop(s, "print_preview", text="")
    header.label(text="Print Preview")
    if sub is not None:
        _draw_print_preview(sub, context)


class CROSSCUT_PT_main(bpy.types.Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Crosscut"
    bl_label = "Crosscut"

    def draw(self, context):
        _draw_main(self.layout, context)
        _draw_settings(self.layout, context)
        info = draw.last_info(_window_region(context))
        if info:
            col = self.layout.column(align=True)
            if info.get("error"):
                col.label(text="Draw error (see console)", icon='ERROR')
            for name in info.get("open", [])[:5]:
                col.label(text=f"Open section: {name}", icon='ERROR')
            for name in info.get("open_mesh", [])[:5]:
                col.label(text=f"Open mesh: {name}", icon='INFO')
            for name in info.get("inside_out", [])[:5]:
                col.label(text=f"Inside out: {name}", icon='ERROR')
            for name in info.get("mixed_normals", [])[:5]:
                col.label(text=f"Flipped faces: {name}", icon='INFO')


class CROSSCUT_PT_popover(bpy.types.Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'HEADER'
    bl_label = "Crosscut"
    bl_ui_units_x = 12

    def draw(self, context):
        _draw_main(self.layout, context)


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
        pie.operator("crosscut.from_view", text="Section from View", icon='VIEW_CAMERA')


def _header_button(self, context):
    if context.scene is None or not hasattr(context.scene, "crosscut"):
        return
    s = context.scene.crosscut
    row = self.layout.row(align=True)
    row.operator("crosscut.toggle", text="", icon='MOD_BOOLEAN', depress=s.mode != 'OFF')
    row.popover(panel="CROSSCUT_PT_popover", text="")


classes = (
    CROSSCUT_PT_main,
    CROSSCUT_PT_popover,
    CROSSCUT_MT_pie,
)


def kc_active_select_mouse():
    prefs = bpy.context.window_manager.keyconfigs.active.preferences
    return getattr(prefs, "select_mouse", 'LEFT')


def _add_keymaps():
    kc = bpy.context.window_manager.keyconfigs.addon
    if kc is None:
        return
    km = kc.keymaps.new(name="3D View", space_type='VIEW_3D')
    kmi = km.keymap_items.new("wm.call_menu_pie", 'B', 'PRESS', shift=True, alt=True)
    kmi.properties.name = "CROSSCUT_MT_pie"
    _keymaps.append((km, kmi))
    # Esc clears pinned measuring lines; with none, the operator's poll lets it through
    kmi = km.keymap_items.new("crosscut.measure_clear", 'ESC', 'PRESS')
    kmi.properties.from_key = True
    _keymaps.append((km, kmi))
    # click-select by section in a zero-thickness slice (the operator passes the
    # click on to Blender's own selection everywhere else)
    try:
        right = kc_active_select_mouse() == 'RIGHT'
    except (AttributeError, KeyError):
        right = False
    button, value = ('RIGHTMOUSE', 'PRESS') if right else ('LEFTMOUSE', 'CLICK')
    for shift in (False, True):
        kmi = km.keymap_items.new("crosscut.select_section", button, value, shift=shift)
        kmi.properties.extend = shift
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
