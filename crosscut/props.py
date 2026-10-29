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


def _start_offset(s):
    """Where a newly chosen plane starts: through an Empty used as the plane,
    else in the middle of the scrub range."""
    if s.orientation == 'OBJECT' and s.plane_object is not None and s.plane_object.type == 'EMPTY':
        return 0.0
    return engine.center_offset(s)


def _orientation_changed(self, context):
    if self.orientation == 'OBJECT' and self.plane_object is None:
        ob = engine.obvious_plane_object(bpy.context)
        if ob is not None:
            self.plane_object = ob
    # a position along the old axis means nothing along the new one: start afresh
    self.offset = _start_offset(self)
    tag_redraw(self, context)


def _plane_object_changed(self, context):
    self.offset = _start_offset(self)
    tag_redraw(self, context)


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
    ('OFF', "Off", "No Crosscut plane (Alt+B clipping still gets caps unless Backfaces is chosen)", 'X', 0),
    ('SECTION', "Section", "Cut the view with a plane and keep one side (half section)", 'MOD_BOOLEAN', 1),
    ('SLICE', "Slice", "Show only a slice: the cross-section itself, or a slab of the given thickness", 'ALIGN_JUSTIFY', 2),
]

ORIENTATIONS = [
    ('X', "X", "Plane normal along world X"),
    ('Y', "Y", "Plane normal along world Y"),
    ('Z', "Z", "Plane normal along world Z"),
    ('OBJECT', "Object", "Use an object as the plane: its local Z axis is the normal, through its origin. "
                         "Move/rotate it with the usual tools. Picked automatically when only one "
                         "Empty, or only one object, is visible"),
    ('VIEW', "View", "Plane facing the view as it was when chosen. It stays put when you orbit; "
                     "click View again to face the current view"),
]

CAP_STYLES = [
    ('BACKFACES', "Backfaces", "No caps: see the inside of the part, like plain Alt+B "
                               "(a zero-thickness slice still shows its outline)"),
    ('SOLID', "Solid", "Fill the cut with a flat colour so solid material reads as solid"),
    ('HATCH', "Hatched", "Fill the cut and add section hatching"),
]


class CrosscutSettings(bpy.types.PropertyGroup):
    mode: EnumProperty(name="Mode", items=MODES, default='OFF', update=tag_redraw)
    last_mode: StringProperty(default='SECTION', options={'HIDDEN'})

    orientation: EnumProperty(name="Orientation", items=ORIENTATIONS, default='Z', update=_orientation_changed)
    view_normal: FloatVectorProperty(size=3, default=(0.0, 0.0, 1.0), options={'HIDDEN'}, update=tag_redraw)
    view_base: FloatProperty(options={'HIDDEN'}, update=tag_redraw)
    placed: BoolProperty(default=False, options={'HIDDEN'},
                         description="The plane has been positioned once (first use starts it in the middle)")
    plane_object: PointerProperty(
        name="Plane Object", type=bpy.types.Object, update=_plane_object_changed,
        description="Object whose local Z axis defines the section plane (no cut until one is chosen)",
    )
    offset: FloatProperty(
        name="Position", subtype='DISTANCE', unit='LENGTH', precision=3, step=10,
        description="Plane position along its normal. For X/Y/Z this is the world coordinate; "
                    "for an Object plane it is measured from the object's origin, for a View "
                    "plane from where it was placed",
        update=tag_redraw,
    )
    position: FloatProperty(
        name="Scrub", subtype='FACTOR', min=0.0, max=1.0, precision=3,
        description="Drag to sweep the plane across the scrub range",
        get=_get_position, set=_set_position,
    )
    scrub_distance: BoolProperty(
        name="Scrub by Distance", default=False,
        description="Show the plane position as a distance instead of a 0-1 slider across the range",
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
        name="Hatch Space", default='MODEL', update=tag_redraw,
        items=[
            ('SCREEN', "Screen", "Constant line spacing in pixels at any zoom"),
            ('MODEL', "Model", "Line spacing in scene units, locked to the part"),
        ],
    )
    hatch_pitch_px: FloatProperty(name="Spacing", min=3.0, max=96.0, default=10.0, precision=1,
                                  description="Hatch spacing in pixels", update=tag_redraw)
    hatch_pitch: FloatProperty(name="Spacing", subtype='DISTANCE', unit='LENGTH', min=1e-4, default=0.5,
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
        description="Highlight areas where two or more objects' sections overlap (red cross-hatching "
                    "by default; see Interference settings)",
    )
    overlap_style: EnumProperty(
        name="Overlaps", default='BLEND', update=tag_redraw,
        items=[
            ('BLEND', "Blend", "Overlapping caps mix their colours equally"),
            ('STRIPES', "Stripes", "Overlapping caps share the area in stripes, one per part"),
        ],
    )
    stripe_width: FloatProperty(name="Stripe Width", subtype='DISTANCE', unit='LENGTH', min=1e-4, default=1.0,
                                precision=3, description="Width of each overlap stripe in scene units",
                                update=tag_redraw)
    stripe_width_px: FloatProperty(name="Stripe Width", min=2.0, max=200.0, default=12.0, precision=1,
                                   description="Width of each overlap stripe in pixels", update=tag_redraw)
    interference_style: EnumProperty(
        name="Style", default='CROSS', update=tag_redraw,
        items=[
            ('SOLID', "Solid", "Flat fill"),
            ('HATCH', "Hatched", "Fill with single hatching"),
            ('CROSS', "Cross", "Fill with cross-hatching"),
        ],
    )
    interference_color: FloatVectorProperty(
        name="Color", subtype='COLOR_GAMMA', size=3, min=0.0, max=1.0, default=(0.86, 0.10, 0.08),
        description="Fill colour of overlapping areas", update=tag_redraw,
    )
    interference_line_color: FloatVectorProperty(
        name="Line Color", subtype='COLOR_GAMMA', size=3, min=0.0, max=1.0, default=(1.0, 0.85, 0.80),
        description="Hatch line colour of overlapping areas", update=tag_redraw,
    )
    interference_opacity: FloatProperty(
        name="Opacity", subtype='FACTOR', min=0.0, max=1.0, default=1.0, update=tag_redraw,
        description="Fill opacity: below 1 the overlapping caps (blended or striped) show through",
    )
    plane_display: EnumProperty(
        name="Plane", default='TINT', update=tag_redraw,
        items=[
            ('NONE', "None", "Don't draw the plane"),
            ('FRAME', "Frame", "Outline the plane around the targets"),
            ('TINT', "Tint", "Outline the plane and tint it"),
            ('HATCH', "Hatched", "Outline the plane, tint it and add light hatching"),
        ],
    )
    plane_color: FloatVectorProperty(
        name="Color", subtype='COLOR_GAMMA', size=3, min=0.0, max=1.0, default=(1.0, 0.75, 0.2),
        description="Colour of the plane frame and tint", update=tag_redraw,
    )
    plane_color_2: FloatVectorProperty(
        name="Second Plane", subtype='COLOR_GAMMA', size=3, min=0.0, max=1.0, default=(0.25, 0.65, 1.0),
        description="Colour of the second plane of a Slice slab, so the two read apart", update=tag_redraw,
    )
    plane_opacity: FloatProperty(
        name="Opacity", subtype='FACTOR', min=0.0, max=1.0, default=0.10, update=tag_redraw,
        description="Tint opacity",
    )
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
