# SPDX-License-Identifier: GPL-3.0-or-later
"""Crosscut: live capped section and slice views for the Blender viewport.

Builds on Blender's own viewport clipping (the same clip planes the clipping region uses) and
draws filled, optionally hatched caps where solids are cut, so a cut solid reads
as solid instead of showing its backfaces.
"""

import bpy
from bpy.app.handlers import persistent

from . import api, draw, engine, ops, props, ui


@persistent
def _on_depsgraph(scene, depsgraph):
    engine.on_depsgraph_update(scene, depsgraph)


@persistent
def _on_load(*args):
    engine.on_load(*args)


@persistent
def _on_undo(*args):
    engine.on_undo(*args)


_handlers = (
    (bpy.app.handlers.depsgraph_update_post, _on_depsgraph),
    (bpy.app.handlers.load_post, _on_load),
    (bpy.app.handlers.undo_post, _on_undo),
    (bpy.app.handlers.redo_post, _on_undo),
)


def register():
    props.register()
    ops.register()
    ui.register()
    draw.register()
    api.register()
    for lst, fn in _handlers:
        if fn not in lst:
            lst.append(fn)


def unregister():
    for lst, fn in _handlers:
        if fn in lst:
            lst.remove(fn)
    api.unregister()
    draw.unregister()
    ui.unregister()
    ops.unregister()
    props.unregister()
    engine.invalidate_all()
