# Changelog

## 0.9.0 (2026-10-29): 1.0 release candidate

- Turning Crosscut off leaves no clipping, instead of bringing back an earlier Alt+B box.
- Object plane: nothing is cut until an object is chosen; the only visible Empty (or the only
  object) is picked automatically; a part can be its own plane and is still capped.
- Click-select parts in a zero-thickness slice.
- Wireframe shading: clipped, no caps or outlines.
- Readout lists visible Wire/Bounds-display solids, which aren't capped.
- Stripe width setting; plane colour, second-plane colour and tint opacity. A slab's planes
  no longer double their tint where you look through both.
- Panel: options that don't apply are hidden rather than greyed out. Cap Targets and Scrub
  Range moved under Settings.
- User guide, changelog, refreshed screenshots.

## 0.4.0 (2026-10-29)

- Overlaps: Blend or Stripes. Interference style, colours and opacity.
- Switching Section or Slice on over an Alt+B box no longer leaves its shading behind.
- Cap Color shown only when used.

## 0.3.0 (2026-10-29)

- New panel layout: Section / Slice buttons (one or neither), cap style row, View plane,
  scrub with step arrows, collapsed sub-panels. The separate Alt+B caps toggle is gone.
- Alt+B: outlines clipped to the box; dragging parts no longer stutters.
- Backfaces + zero-thickness slice shows the section. Overlapping caps blend. Plane tint.
- Defaults: model-space hatching at 0.5, plane starts mid-range.

## 0.2.0 (2026-10-29)

- First build tested in Blender. Clipping works without pressing Alt+B first; correct
  colours; a new section shows its cut face; open meshes fill sensibly; readout uses scene
  units.

## 0.1.0 (2026-10-22)

- First version, written without access to Blender.
