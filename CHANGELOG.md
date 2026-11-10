# Changelog

## 0.16.1 (2026-11-09)

- Fixed: Blender crashed when Crosscut was turned on in Edit Mode under Material Preview. Clipping now waits until the
  view is in Solid or Wireframe, the only shadings Blender clips in.
- In Blender 5, the header button sits between X-ray and the shading buttons. In 4.2 it stays at the right end.
- Print Preview is no longer called experimental.

## 0.16.0 (2026-11-04)

- **Measure**: while placing a line, the free end snaps straight across from the edge the anchor sits on, within
  about 10 pixels of that direction, with a small square-corner mark at the anchor. Hold **Ctrl** to turn it off.
- **Print Preview** has a **Printer** choice. **MJF 580** (a first try) draws each part's surface color along the
  inside edge of its fused layer, from its image texture or flat material color, **Color Depth** deep and never thinner
  than 2 pixels. **FDM** is only a placeholder for now: it draws like the 5600 and links to its issue.

## 0.15.1 (2026-11-04)

- Fixed: Measure's lines stayed on screen with overlays off (Alt+Shift+Z), though their lengths hid.

## 0.15.0 (2026-11-04)

- **Measure**: while placing a line, it follows the cursor directly. Inside the section the line runs through
  the cursor to the edge beyond; outside it, the end goes to the nearest point on the edge.
- Measure's lengths follow **Hatch Space**: in Model space they're a height in scene units and scale with the view; in
  Screen space they stay a fixed size.
- **Esc** stops Measure and leaves pinned lines on screen; a further Esc clears them. Next to the Measure button,
  **X** clears them, and the pin (**Keep Pinned Lines**) makes them survive Esc.

## 0.14.1 (2026-11-04)

- **Measure**: an anchored line now sweeps like a beam around the section, so the free end follows onto adjacent
  edges and round corners, instead of stopping at the end of the opposite edge.

## 0.14.0 (2026-11-04)

- **Measure**: click a line to anchor its nearer end; moving the mouse slides the other end along the contour.
  A second click pins it, and you can carry on and pin more. Esc while placing drops that line; otherwise it
  clears them all and stops.
- **Brightness** of fill colors now defaults to 50 %.
- **Cut Faces** settings are grouped with rules: which parts, their color, the lines on them, overlaps. Open Part
  Opacity moved up beside Fill Opacity.

## 0.13.0 (2026-11-03)

- Fixed: **weight painting did nothing** with Section, Slice or a clipping region on, and neither did other tools
  that test against Blender's clipping box. They now work on what's kept, and only there.
- **Measure** (was Measure Overlap) works on any cut: hover over a part for its thickness at the mouse, or over an
  overlap for its width. **Section Max** (off by default) adds the section's greatest thickness; **Ignore
  Overlaps** (off) always measures one part. **Overlap Max** can be turned off too.
- Measure's two lines have their own default colors, light blue at the mouse and orange for the max, with
  dark outlines on the lengths.
- **Fill colors** that come from the parts can be adjusted: **Saturation**, **Brightness** and **Tint**, plus
  **Fill Opacity**. By default they're now a little grayer and darker, closer to the shaded surfaces around them.
- Clicking a lit **X**, **Y**, **Z**, **Object** or **View** turns the plane off, as Section and Slice do. View no
  longer re-aims on a second click: turn it off and on.
- Fixed: **Clip Tint** tinted the whole screen in an orthographic view, so it looked like nothing.
- Fixed: a zero-thickness slice read red from one side with Face Orientation on. It has no inside, so neither side does.
- Scrub Range's **Targets** is now **Fill Targets**.

## 0.12.0 (2026-11-03)

- **Measure Overlap** shows two measures: the overlap's greatest depth (labelled "max") and its width right
  where the mouse is, roughly tangent to tangent (**Local Width**, on by default). It has its own settings for
  color and text size.
- **Print Preview**: no outlines through parts' interiors. **Slice** now differs from Section: one layer
  of powder, or with Slice Thickness a band of it, rather than the whole bed.
- **Clip Tint** can be turned off and on at any time, survives Section and Slice, and follows a scrub.
- Back on its own **Crosscut** tab, as one panel. Settings sits closer to the main controls, and its first
  three options are left-aligned.
- **Slice Thickness** moved into Section/Slice Plane.
- Scrub row: left, cursor, center, selection, right, as small buttons; the row below is gone.
- The **Caps** section is now **Cut Faces**, its **Cap** row **Fill**, and **Cap Color** **Fill Color**.

## 0.11.0 (2026-11-03)

- **Clip remembers**: switching to Section or Slice and clicking Clip again brings your box back, where
  you left it. Clicking Clip while it's lit removes the box for good.
- **Overlaps** has a third option, **Highlight**, with its style, colours and opacity right below.
  It replaces the separate Interference panel and its checkbox.
- **Scrub** has a 0.5 button between its arrows.
- **Caps** starts with **Cap**: Visible Objects, Selected Objects or Collection (was the Cap Targets panel).
- **Section/Slice Plane** (was Plane) holds the scrub settings at its top (was Scrub Settings).
- Cut outlines stay dark on problem parts, including red-capped ones; the readout does the warning.

## 0.10.0 (2026-11-03)

The add-on is in development: expect changes before 1.0.

- **Moved to the sidebar's View tab**, with Settings folded into the main panel.
- **Measure Overlap**: hover over an overlap on a cut to see how deep it goes, with a dimension line.
- **Clipping region**: two sliders, one per axis (labelled with the nearest world axis), which don't
  flip or relabel as the view turns. The mouse wheel uses the axis facing you.
- Blender's faint clipping box is gone by default (**Clip Tint** brings it back until you scrub).
- **Inside-out parts** are named in red, and mixed normals in amber. **Face Orientation** has a toggle
  in Settings, and with it on, a cap seen from inside a part reads as a backface.
- Hatching: **Scale with Part** makes spacing follow part size in Model space.
- Cap colours match Solid shading's **Random** colours.
- Fixed: annotations disappeared behind caps once drawn.
- Fixed: open contours drew in orange and looked selected; they're now red, like the warning, and only
  with overlays on.
- Turning overlays off (Alt+Shift+Z) hides the plane and the readout.
- "Alt+B" in the interface is now Clip or Clipping Region, as in Blender.

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
