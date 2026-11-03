# Changelog

## 0.9.4 (2026-11-02)

- Fixed: overlapping closed shells inside one object cancelled out and left a hole in the cap
  (Suzanne's head and eyes). They now stay filled; shells with reversed normals still cut holes.
  Clicking a part in a zero-thickness slice follows the same rule.
- **Scrub an Alt+B box**: with Clip on, a slider and step buttons slide the box along whichever of its
  axes faces you most. Its size stays the same.
- **X, Y, Z and Object** now start a section while Crosscut is off, as View does.
- **Print Preview** (experimental) is in Settings: powder fills the bed up to the plane and the cut
  through each part is the fused layer, in one colour. Powder and fused colours and powder grain are
  adjustable. The bed is the Scrub Range object, or the targets' bounds plus a margin. The readout
  counts layers ("layer 512 / 1150") at the Step size.

## 0.9.3 (2026-11-02)

- The plane row is back while Crosscut is off: View starts a section from there.
- The Alt+B button is now **Clip**, first in the row.
- Fixed: the Clip button stayed lit (or unlit) after Alt+B on the keyboard, until you hovered over it.

## 0.9.2 (2026-11-02)

- Fixed: overlapping caps z-fought in bands, with interference on or off (came in with 0.9.1),
  and caps z-fought with a flat face lying on the plane.
- Fixed: a selected part with a face on the plane lost its outline under a neighbour's contour.
- **Alt+B button** next to Section and Slice: lit while a box is on; click to draw or remove one.
- **Object plane**: choose the object's local X, Y or Z axis. Object picks the selected part when
  no single Empty is visible. **+** no longer moves a part used as the plane.
- **Open meshes** warn whenever a cut goes through one, even if the hole isn't on the plane, and
  their caps are translucent (Open Part Opacity). An open contour on the plane warns in red.
- **X-ray** (Alt+Z): caps go translucent like the parts.
- **Vary per Object** stays put when parts are hidden, shown or added.
- The readout moved to the bottom centre, clear of Blender's Adjust Last Operation panel.
- Panels: the plane row hides while Crosscut is off; Scrub by Distance and Step moved into Scrub
  Settings (was Scrub Range); Cap Targets sits right under Caps.

## 0.9.1 (2026-10-29)

- Selected parts' cut contours show in the selection colour, so selection is visible in a
  zero-thickness slice and matches Blender's outline in a slab.
- A slab's far contour no longer shows through the near cap; the plane frame is hidden behind
  parts.
- Outline, open-contour and frame colours now match the colours set (they came out darker).
- Choosing Object with a plane object that is hidden or gone picks again instead of keeping it.
- Plane tint: default opacity 3 %, slider up to 10 % (type up to 100 %).
- Panels: everything beyond the main controls is in a separate Settings panel, closed by
  default, with Caps, Plane, Cap Targets and Scrub Range inside.

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
