# Where Crosscut goes next (2026-11-12)

A proposal, written after the [audit](AUDIT.md). Nothing here is built. Items marked **Decided** are my
recommendation with the reason; items marked **Your call** are real choices for the maintainer.

## What Crosscut is

**The inspection view for print builds: look inside, layer by layer, and answer "is this OK?" on the
spot.** It is not a drafting tool (no dimensioned drawings) and not a slicer.

That gives one rule for dividing work with Bucket Builder:

- **Crosscut looks and probes.** It shows what a plane shows, and measures in that plane.
- **Bucket Builder checks and enforces.** Anything that needs the whole 3D shape (true closest distance
  between parts, thinnest wall anywhere on a part) is an analysis, and belongs with the checks.
- They meet in one place: **Bucket Builder finds a problem, Crosscut shows it** (below).

## Measure

### What a measurement is

**Decided: a measurement is two points, each attached to a part, plus the plane it was taken in.** Its
value is the distance between the two points, worked out fresh every time it is drawn.

- Not a point in space: world points go stale the moment a part moves, and in a build parts move all
  the time (packing, Jiggle).
- Not attached to the clipping plane: the plane is the tool that exposed the spot, not what was
  measured. But the plane is remembered, so Crosscut can take you back to it.
- Each end stores the object and the point in that object's own coordinates. An end with no part under
  it stores a world point.

There are three kinds, and they are one tool, since each is "the line straight across, at the mouse":

| Kind | Mouse is over | Answers |
|---|---|---|
| Thickness | one part's cut face | how thick is this wall? |
| Overlap | two parts' cut faces | how deep do these interfere? |
| **Gap** (new) | empty space between two contours | how far apart are these walls or parts? |

Gap is the missing one, and the one MJF work asks for most: the space between neighbours in a build,
a print-in-place hinge, a slot, a hole. It is the Thickness search with inside and outside swapped, so
it is cheap to add.

### What happens when things change

| Change | Thickness (both ends on one part) | Gap or Overlap (ends on two parts) |
|---|---|---|
| A part moves or rotates | The line travels with the part. The value can't change. | The line stretches between its two points. The value updates live. |
| A part's mesh is edited | Marked stale: dimmed, value shown with "?". | The same. |
| The clipping plane moves | Nothing. The line belongs to the parts. | Nothing. |
| A part is deleted | The measurement goes with it. | The same. |

- **Decided: a gap is a tape between two marked spots**, not "the shortest distance, found again". It is
  predictable, it costs two matrix multiplications per line, and it never jumps to another place. The
  true closest distance between two parts is Bucket Builder's job.
- **Decided: a stale line is kept and marked, never silently moved or deleted.** One click re-snaps its
  ends to the nearest contour in its plane; another deletes it.
- **Decided: lines on the current plane draw in full; the others draw dimmed.** Each has a "go to"
  button that puts the plane back where the line was taken. Measurements then double as bookmarks of
  the sections worth looking at. *Your call:* dimmed (my choice) or hidden when the plane is elsewhere.

### One thing a section can't tell you

**Every measurement in a plane is an upper bound.** A wall cut at a slant looks thicker than it is, and
two parts look farther apart than they are, unless the plane happens to be square to them. Snapping
"straight across" (D-041) fixes this inside the plane only.

- **Decided:** say so in the user guide, and never label an in-plane gap "clearance".
- **Your call: show the true wall thickness too.** At each end Crosscut knows which triangle the contour
  came from, so it knows how the wall leans. When both walls are parallel (within about 10 degrees) the
  true thickness is the line's length times the cosine of the lean, exact for flat walls. I'd show it
  as a second number, "2.31 mm (wall 2.05)", only when it differs by more than 2 %. It is a small
  addition that makes the number trustworthy; the cost is one more thing to explain.

### Which measurements matter for MJF

1. **Gaps between parts in a build**: Bucket Builder owns the number (3D, every pair). Crosscut is for
   looking at the tight spots and for hand checks.
2. **Wall thickness**: thin walls break or don't resolve, thick masses hold heat and sink. Measure
   answers it one spot at a time.
3. **Gaps inside a part or assembly**: hinges, snap fits, slots, powder escape holes.
4. **Overlap depth**: already there.

**Decided: lines get a pass / fail colour.** Two limits, minimum wall and minimum gap: a thickness or
gap below its limit draws red. The limits come from the shared printer file (portfolio decision D2)
when it has them, else from two Crosscut settings. A number you have to compare in your head becomes
an answer.

### Saving (#12)

**Decided: a collection on the Scene, one entry per measurement:** kind, two ends (object pointer and
local point, or a world point), the plane, a name, shown or hidden. Operators write it; drawing only
reads it.

- This differs from the recommendation on #12 (world points only). Attachment costs little now, since
  the tool already knows which part is under each end, and changing the stored format later means
  converting people's files.
- It gives save, undo and append for free, and removes the bug where undo deletes pinned lines (audit
  finding 10).
- The panel gets a short list: name, value, eye, go to, delete. "Copy as text" covers reports. Esc no
  longer clears lines; the list does.

### Where Measure meets Bucket Builder

**Decided: one operator, `crosscut.show_pair`, taking two world points and a label.** Bucket Builder
calls it from a problem's row ("Show in section") when Crosscut is installed. Crosscut puts a plane
through both points, facing the view as far as it can, and draws the pair as a measurement marked as
coming from a check (not saved, not editable).

- Bucket Builder already has the closest points of each tight pair, or can get them cheaply.
- Neither add-on imports the other, in line with portfolio decision D1.
- This replaces the "list which parts interfere over the whole range" idea in #5. Bucket Builder
  already does that in 3D and better; Crosscut sweeping planes to find overlaps would be a second,
  weaker collision check.

### What Measure will not become

No angles, radii, leader lines, tolerances or drawing sheets. If a wish needs any of those, it's a
drawing tool, and Blender has add-ons for that (MeasureIt).

## Crosscut as a whole

### What's missing, in order of value

1. **Speed on a full build.** The audit's first four findings. Until a 500-part bucket scrubs smoothly
   on the laptop, the rest is polish on a tool that only works on small scenes.
2. **Measurements that last**, as above.
3. **Working as one tool with Bucket Builder**: the build volume as the scrub range without picking
   it, layer numbers as the printer counts them (both from #5), `show_pair`, the shared printer file,
   the agreed draw order (#17).
4. **Windows.** Colleagues and the send-to-printer work are on Windows, and it has never been run
   there (#7). The Windows VM makes this a day's work.
5. **Getting a section out**: an SVG or DXF of the contours with the measurements, for a report to
   whoever designed the part (#2).

### Options worth a decision

- **Your call: a thin-wall highlight on the cut face.** Colour the cut face where the section is
  thinner than the minimum wall, so thin spots light up while scrubbing, with no clicking. Strong for
  a quick look. Its weakness is the upper-bound problem above: slanted thin walls are missed. A check
  that can't miss needs the 3D shape, which makes it a Bucket Builder check (near #29). I'd build the
  3D check first and this highlight only if the quick look is still missed afterwards.
- **Your call: a fused-area profile.** The area of every layer of the build, as a small graph beside
  the scrub slider. In powder-bed printing, layers with a large or suddenly changing fused area are
  where heat trouble starts. Crosscut has everything needed (area comes straight from the contours).
  Whether operators would use it is your field knowledge, not mine.
- **Later, low priority:** a section box and several planes at once (#1), per-object fill overrides
  (#3), FDM preview (#13, remove the placeholder until someone builds it).
- **With more time, upstream:** a small patch to Blender so add-ons can switch clip planes on without
  the clipping-box workaround. It would delete the most fragile 150 lines in the add-on.

### Releases

| Release | Theme | Contents | Done when |
|---|---|---|---|
| 0.17 | Scale | Benchmark script; shared mesh cache; bounded GPU passes; offscreen sizes; stale view state; undo keeps lines; #17; #18; wording | The benchmark's before and after are in the docs |
| 0.18 | Measurements that last | Saved, attached measurements; the list with go to; Gap; stale marking; pass / fail colours; #15 | A file with measurements survives save, reload, undo and a packing run |
| 0.19 | One toolset | `show_pair`; build volume as range; printer layer numbers; shared printer file | A Bucket Builder problem opens as a section in one click |
| 0.20 | Solid ground | Windows and HiDPI tested; numpy tests in CI; scrub index (#4); `draw.py` split | The suite passes on Windows |
| 1.0 | Release | User guide and demo current; no bug older than one release | The bar below is met |
| after | | Section export; thin-wall highlight or fused-area profile, if chosen; section box | |

**Your call: the bar for 1.0.** My proposal: a 500-part build scrubs at 20 frames a second or better on
the laptop, Windows is tested, measurements are saved, and you have used it on real builds for two
weeks without filing a bug. The part count and frame rate should come from your real buckets.

## Requested vs. assumed

- **Requested:** a vision for Measure (what a measurement is, what happens on changes, which ones
  matter for MJF, saving, the link to Bucket Builder's checks), then briefly Crosscut as a whole with
  releases and milestones.
- **Assumed:** that Bucket Builder can hand over the closest points of a tight pair; that minimum wall
  and minimum gap can live in the shared printer file; the release numbering and order; that Esc no
  longer clearing lines is acceptable once there is a list.
- **Questions not asked:** how often you measure the same spot again after moving parts; whether
  reports to part designers are a real need; typical part count and triangle count of a build.
- **Follow-ups:** the choices marked "Your call" above; agreement from the Bucket Builder session on
  `show_pair` and on the draw order (#17).
