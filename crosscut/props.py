# SPDX-License-Identifier: GPL-3.0-or-later
"""Scene settings. Stored on the Scene so they save with the .blend."""

import math

import bpy
from bpy.props import (
    BoolProperty,
    EnumProperty,
    FloatProperty,
    FloatVectorProperty,
    PointerProperty,
    StringProperty,
)

from . import engine


def tag_redraw(_self=None, _context=None):
    """Push the settings to every 3D view now and redraw them."""
    wm = bpy.context.window_manager
    if wm is None:
        return
    from . import draw
    try:
        draw.sync_views()
    except Exception as ex:  # noqa: BLE001 - the draw callback retries and reports
        print("Crosscut: sync failed:", ex)
    for win in wm.windows:
        for area in win.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()


def _get_position(self):
    lo, hi = engine.scrub_range(self)
    if hi - lo <= 1e-12:
        return 0.5
    c = engine.plane_coordinate(self)
    if c is None:
        return 0.5
    return min(1.0, max(0.0, (c - lo) / (hi - lo)))


def _set_position(self, value):
    lo, hi = engine.scrub_range(self)
    if hi - lo <= 1e-12:
        return
    base = engine.plane_base(self)
    if base is None:
        return
    self.offset = lo + value * (hi - lo) - base


MODES = [
    ('OFF', "Off", "No Crosscut clipping (native Alt+B clipping still gets caps if enabled)", 'X', 0),
    ('SECTION', "Section", "Cut the view with a plane and keep one side (half section)", 'MOD_BOOLEAN', 1),
    ('SLICE', "Slice", "Show only a slice: the cross-section itself, or a slab of the given thickness", 'ALIGN_JUSTIFY', 2),
]

ORIENTATIONS = [
    ('X', "X", "Plane normal along world X"),
    ('Y', "Y", "Plane normal along world Y"),
    ('Z', "Z", "Plane normal along world Z"),
    ('OBJECT', "Object", "Use an object (usually an Empty) as the plane: its local Z axis is the normal. "
                         "Move/rotate it with the usual tools"),
]

CAP_STYLES = [
    ('BACKFACES', "Backfaces", "No cap: see the inside of the part, like plain Alt+B"),
    ('SOLID', "Solid", "Fill the cut with a flat colour so solid material reads as solid"),
    ('HATCH', "Hatched", "Fill the cut and add section hatching"),
]


class CrosscutSettings(bpy.types.PropertyGroup):
    mode: EnumProperty(name="Mode", items=MODES, default='OFF', update=tag_redraw)
    last_mode: StringProperty(default='SECTION', options={'HIDDEN'})

    orientation: EnumProperty(name="Orientation", items=ORIENTATIONS, default='Z', update=tag_redraw)
    plane_object: PointerProperty(
        name="Plane Object", type=bpy.types.Object, update=tag_redraw,
        description="Object whose local Z axis defines the section plane",
    )
    offset: FloatProperty(
        name="Offset", subtype='DISTANCE', unit='LENGTH', precision=3, step=10,
        description="Plane position along its normal. For X/Y/Z this is the world coordinate; "
                    "for an Object plane it is measured from the object's origin",
        update=tag_redraw,
    )
    position: FloatProperty(
        name="Scrub", subtype='FACTOR', min=0.0, max=1.0, precision=3,
        description="Drag to sweep the plane across the scrub range",
        get=_get_position, set=_set_position,
    )
    flip: BoolProperty(name="Flip", description="Keep the other side of the plane", update=tag_redraw)
    thickness: FloatProperty(
        name="Thickness", subtype='DISTANCE', unit='LENGTH', min=0.0, default=0.0, precision=3,
        description="Slab thickness for Slice mode, centred on the plane. 0 shows only the cross-section",
        update=tag_redraw,
    )
    step: FloatProperty(
        name="Step", subtype='DISTANCE', unit='LENGTH', min=1e-6, default=0.08, precision=3,
        description="Distance moved by the step buttons and Shift+Alt+Wheel "
                    "(0.08 = one MJF layer when 1 unit = 1 mm)",
    )

    cap_style: EnumProperty(name="Cap", items=CAP_STYLES, default='HATCH', update=tag_redraw)
    last_cap_style: StringProperty(default='HATCH', options={'HIDDEN'})
    cap_native: BoolProperty(
        name="Cap Alt+B Clipping", default=True, update=tag_redraw,
        description="Also draw caps for Blender's own clipping region (Alt+B) while Crosscut is Off",
    )

    targets: EnumProperty(
        name="Targets", default='VISIBLE', update=tag_redraw,
        items=[
            ('VISIBLE', "Visible", "Cap every visible solid object"),
            ('SELECTED', "Selected", "Cap only selected objects (everything is still clipped)"),
            ('COLLECTION', "Collection", "Cap only objects in a collection"),
        ],
    )
    target_collection: PointerProperty(name="Collection", type=bpy.types.Collection, update=tag_redraw)

    color_source: EnumProperty(
        name="Colors", default='AUTO', update=tag_redraw,
        items=[
            ('AUTO', "Auto", "Follow the Solid shading colour (Object or Material); white or grey parts get "
                             "the Cap Color so the cut stands out; other shading colours use a per-object palette"),
            ('OBJECT', "Object", "Object viewport display colour"),
            ('MATERIAL', "Material", "First material's viewport display colour"),
            ('PALETTE', "Palette", "Distinct colour per object"),
            ('SINGLE', "Single", "One colour for every cap"),
        ],
    )
    single_color: FloatVectorProperty(
        name="Cap Color", description="Cap colour for Single, and for white or grey parts in Auto", subtype='COLOR_GAMMA', size=3, min=0.0, max=1.0,
        default=(0.29, 0.47, 0.25), update=tag_redraw,
    )
    hatch_space: EnumProperty(
        name="Hatch Space", default='SCREEN', update=tag_redraw,
        items=[
            ('SCREEN', "Screen", "Constant line spacing in pixels at any zoom"),
            ('MODEL', "Model", "Line spacing in scene units, locked to the part"),
        ],
    )
    hatch_pitch_px: FloatProperty(name="Spacing", min=3.0, max=96.0, default=10.0, precision=1,
                                  description="Hatch spacing in pixels", update=tag_redraw)
    hatch_pitch: FloatProperty(name="Spacing", subtype='DISTANCE', unit='LENGTH', min=1e-4, default=2.0,
                               precision=3, description="Hatch spacing in scene units", update=tag_redraw)
    hatch_angle: FloatProperty(name="Angle", subtype='ANGLE', default=math.radians(45.0), update=tag_redraw)
    hatch_width: FloatProperty(name="Line Width", subtype='FACTOR', min=0.05, max=0.9, default=0.3,
                               description="Hatch line width as a fraction of the spacing", update=tag_redraw)
    hatch_vary: BoolProperty(
        name="Vary per Object", default=True, update=tag_redraw,
        description="Alternate hatch direction, then spacing, between objects (ISO 128-50 style) "
                    "so touching or overlapping sections stay distinguishable",
    )
    outline: BoolProperty(name="Outline", default=True, update=tag_redraw,
                          description="Draw the cut contour")
    outline_width: FloatProperty(name="Width", min=0.5, max=6.0, default=1.5, update=tag_redraw)
    interference: BoolProperty(
        name="Show Interference", default=True, update=tag_redraw,
        description="Highlight areas where two or more objects' sections overlap",
    )
    show_frame: BoolProperty(name="Plane Frame", default=True, update=tag_redraw,
                             description="Outline the section plane around the targets")
    show_readout: BoolProperty(name="Readout", default=True, update=tag_redraw,
                               description="Show the plane position and warnings in the viewport")

    range_source: EnumProperty(
        name="Scrub Range", default='TARGETS', update=tag_redraw,
        items=[
            ('TARGETS', "Targets", "Scrub across the bounds of the targets"),
            ('OBJECT', "Object", "Scrub across an object's bounds (e.g. a build volume). "
                                 "The object is excluded from capping"),
        ],
    )
    range_object: PointerProperty(name="Range Object", type=bpy.types.Object, update=tag_redraw)


def register():
    bpy.utils.register_class(CrosscutSettings)
    bpy.types.Scene.crosscut = PointerProperty(type=CrosscutSettings)


def unregister():
    del bpy.types.Scene.crosscut
    bpy.utils.unregister_class(CrosscutSettings)
