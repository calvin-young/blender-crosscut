# Crosscut API for other add-ons

Other add-ons can show, move and clear a Crosscut section without importing Crosscut. Why it works this way:
[DECISIONS.md](DECISIONS.md), D-054.

```python
api = bpy.app.driver_namespace.get("crosscut")      # None when Crosscut isn't enabled
if api is not None and api.API_VERSION >= 1:
    if not api.set_section(z, owner="my_addon"):
        ...  # the user's own section is showing: leave it
    ...
    api.clear_section("my_addon")
```

| Call | Does |
|---|---|
| `set_section(z, normal=(0, 0, 1), collection=None, owner="", force=False, scene=None)` | Section at offset `z` along `normal` (scene units), keeping the side against the normal: for the default, everything below height `z`. |
| `set_slab(z0, z1, normal=(0, 0, 1), collection=None, owner="", force=False, scene=None)` | Slice mode: only what lies between `z0` and `z1`. Equal values show the cross-section alone. |
| `clear_section(owner, scene=None)` | Removes the owner's section and puts back the user's settings from before its first call. |
| `section_info(scene=None)` | `None`, or `{"mode", "owner", "normal", "offset", "thickness"}`. `mode` is `'SECTION'`, `'SLICE'` or `'CLIP'` (the user's Alt+B region); `owner` is `""` for the user. |

- `owner` is required: your add-on's name. `set_*` and `clear_section` return `False` and change nothing when the
  section showing isn't yours. `force=True` overrides that; don't use it from a plain button.
- Your first `set_*` saves the user's settings; later calls just move the plane. The user can scrub your section.
  If they turn it off, switch mode or change axis, it's theirs from then on.
- `collection` limits the filled cut faces to its objects. Everything is still clipped: that's how Blender's clip
  planes work.
- Any non-zero `normal` works. X, Y and Z (either sign) use the axis orientations, others the View orientation.
